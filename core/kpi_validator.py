"""
Skout — Pattern #3: KPI Validator
===================================
Validates supply chain recommendations against industry KPI benchmarks.

Extracts KPI mentions from recommendation text, checks proposed changes against
benchmark ranges, and raises warnings when a recommendation would push a KPI
outside safe bounds.

Usage:
    validator = KPIValidator(industry="automotive")
    warnings = validator.validate(recommendation_text)
    for w in warnings:
        print(w["kpi"], w["severity"], w["message"])
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple


_BENCHMARKS_FILE = Path(__file__).parent.parent / "domain_knowledge" / "kpi_benchmarks.json"


@dataclass
class KPIWarning:
    """
    A single KPI benchmark violation or caution raised by the KPI Validator.

    Attributes:
        kpi_id:          Machine-readable KPI identifier from kpi_benchmarks.json.
        kpi_name:        Human-readable KPI name (e.g. "Forecast Accuracy").
        severity:        Warning level: RED (critical violation) / AMBER (caution) / INFO.
        message:         Explanation of why this recommendation may push the KPI out of bounds.
        benchmark:       Industry benchmark range dict {min, max, ideal} for reference.
        triggered_by:    The keyword or phrase in the recommendation text that triggered this.
        recommendation:  Actionable corrective guidance for the PM.
    """
    kpi_id: str
    kpi_name: str
    severity: str          # RED / AMBER / INFO
    message: str
    benchmark: Dict
    triggered_by: str      # The phrase in the text that triggered this
    recommendation: str    # What the validator recommends instead

    @property
    def severity_emoji(self) -> str:
        """Emoji icon for the severity level: 🔴 RED, 🟡 AMBER, 🔵 INFO."""
        return {"RED": "🔴", "AMBER": "🟡", "INFO": "🔵"}.get(self.severity, "⚪")

    def to_dict(self) -> Dict:
        """Serialise warning fields (including severity_emoji) to a plain dict for JSON export."""
        return {
            "kpi_id": self.kpi_id,
            "kpi_name": self.kpi_name,
            "severity": self.severity,
            "severity_emoji": self.severity_emoji,
            "message": self.message,
            "triggered_by": self.triggered_by,
            "recommendation": self.recommendation,
        }


class KPIValidator:
    """
    Validates recommendations against industry KPI benchmarks.
    Industry defaults to 'default' if not specified.
    """

    KNOWN_INDUSTRIES = {
        "retail": "retail",
        "automotive": "automotive",
        "auto": "automotive",
        "pharma": "pharma",
        "pharmaceutical": "pharma",
        "food": "food_beverage",
        "food and beverage": "food_beverage",
        "food_beverage": "food_beverage",
        "fmcg": "food_beverage",
        "electronics": "electronics",
        "tech": "electronics",
        "industrial": "industrial",
        "manufacturing": "industrial",
    }

    def __init__(self, industry: str = "default"):
        """
        Initialise the validator for a specific industry.

        Args:
            industry: Industry name or alias (e.g. "automotive", "auto", "pharma").
                      Normalised via KNOWN_INDUSTRIES; falls back to "default" benchmarks
                      if the industry is not in the map.
        """
        self._benchmarks = self._load_benchmarks()
        self.industry = self.KNOWN_INDUSTRIES.get(industry.lower(), industry)

    def _load_benchmarks(self) -> Dict:
        """
        Load KPI benchmark data from domain_knowledge/kpi_benchmarks.json.

        Returns:
            Parsed benchmark dict with top-level "kpis" key.
            Returns {"kpis": {}} if the file does not exist.
        """
        if not _BENCHMARKS_FILE.exists():
            return {"kpis": {}}
        with open(_BENCHMARKS_FILE, encoding="utf-8") as f:
            return json.load(f)

    def _get_range(self, kpi_data: Dict) -> Dict:
        """Get industry-specific range, fall back to default."""
        ranges = kpi_data.get("industry_ranges", {})
        return ranges.get(self.industry) or ranges.get("default", {})

    # ---------------------------------------------------------------- #
    # Pattern detection helpers
    # ---------------------------------------------------------------- #

    _REDUCTION_PATTERNS = [
        r"reduc[e|ing|tion]\s+(?:by\s+)?(\d+)\s*%",
        r"cut\s+(?:by\s+)?(\d+)\s*%",
        r"decreas[e|ing]\s+(?:by\s+)?(\d+)\s*%",
        r"lower\s+(?:by\s+)?(\d+)\s*%",
        r"down\s+(?:by\s+)?(\d+)\s*%",
        r"(\d+)\s*%\s+reduction",
        r"(\d+)\s*%\s+decrease",
    ]

    _INCREASE_PATTERNS = [
        r"increas[e|ing]\s+(?:by\s+)?(\d+)\s*%",
        r"improv[e|ing]\s+(?:by\s+)?(\d+)\s*%",
        r"rais[e|ing]\s+(?:by\s+)?(\d+)\s*%",
        r"up\s+(?:by\s+)?(\d+)\s*%",
        r"(\d+)\s*%\s+increase",
        r"(\d+)\s*%\s+improvement",
        r"(\d+)x\s+(?:faster|better)",
    ]

    def _find_percentage_change(self, text: str) -> Tuple[Optional[float], str]:
        """Returns (pct_change, direction) where direction is 'decrease' or 'increase'."""
        text_lower = text.lower()
        for pat in self._REDUCTION_PATTERNS:
            m = re.search(pat, text_lower)
            if m:
                return float(m.group(1)), "decrease"
        for pat in self._INCREASE_PATTERNS:
            m = re.search(pat, text_lower)
            if m:
                return float(m.group(1)), "increase"
        return None, "unknown"

    def _mentions_kpi(self, text: str, keywords: List[str]) -> Optional[str]:
        """Return the first matching keyword found in text, or None."""
        text_lower = text.lower()
        for kw in keywords:
            if kw.lower() in text_lower:
                return kw
        return None

    # ---------------------------------------------------------------- #
    # Core validation logic
    # ---------------------------------------------------------------- #

    def validate(self, recommendation_text: str) -> List[KPIWarning]:
        """
        Scan recommendation text for KPI-related claims and validate them
        against industry benchmarks.
        """
        if not recommendation_text:
            return []

        warnings: List[KPIWarning] = []
        kpis = self._benchmarks.get("kpis", {})

        for kpi_id, kpi_data in kpis.items():
            keyword_hit = self._mentions_kpi(
                recommendation_text,
                kpi_data.get("keywords", [])
            )
            if not keyword_hit:
                continue

            kpi_name = kpi_id.replace("_", " ").title()
            benchmark_range = self._get_range(kpi_data)
            if not benchmark_range:
                continue

            pct_change, direction = self._find_percentage_change(recommendation_text)
            direction_intent = kpi_data.get("direction", "higher_is_better")
            red_flag_changes = kpi_data.get("red_flag_changes", [])

            warning = self._evaluate_kpi(
                kpi_id=kpi_id,
                kpi_name=kpi_name,
                kpi_data=kpi_data,
                benchmark_range=benchmark_range,
                pct_change=pct_change,
                direction=direction,
                direction_intent=direction_intent,
                keyword_hit=keyword_hit,
                red_flags=red_flag_changes,
            )
            if warning:
                warnings.append(warning)

        # Sort: RED first, then AMBER, then INFO
        severity_order = {"RED": 0, "AMBER": 1, "INFO": 2}
        warnings.sort(key=lambda w: severity_order.get(w.severity, 3))
        return warnings

    def _evaluate_kpi(
        self,
        kpi_id: str,
        kpi_name: str,
        kpi_data: Dict,
        benchmark_range: Dict,
        pct_change: Optional[float],
        direction: str,
        direction_intent: str,
        keyword_hit: str,
        red_flags: List[str],
    ) -> Optional[KPIWarning]:
        """Determine if there is a warning for this KPI mention."""

        direction_intent = kpi_data.get("direction", "higher_is_better")

        # Special checks for known high-risk KPIs
        if kpi_id == "inventory_turnover" and direction == "increase" and pct_change and pct_change > 50:
            return KPIWarning(
                kpi_id=kpi_id,
                kpi_name=kpi_name,
                severity="RED",
                message=(
                    f"Inventory turnover increase of {pct_change:.0f}% is extreme. "
                    f"Industry ideal for {self.industry} is {benchmark_range.get('ideal', 'N/A')}x. "
                    "Sudden large turnover increases signal safety stock erosion and stockout risk."
                ),
                benchmark=benchmark_range,
                triggered_by=keyword_hit,
                recommendation="Cap inventory turnover improvement at 20-25% year-over-year and validate safety stock levels remain adequate.",
            )

        if kpi_id == "safety_stock_reduction" or (kpi_id == "inventory_turnover" and direction == "increase"):
            return KPIWarning(
                kpi_id=kpi_id,
                kpi_name=kpi_name,
                severity="AMBER",
                message=(
                    f"Recommendation mentions '{keyword_hit}'. Benchmark ideal for {self.industry} "
                    f"is {benchmark_range.get('ideal', 'N/A')} {kpi_data.get('unit', '')}. "
                    f"Verify lead time variance (CV) is below 15% before reducing buffers."
                ),
                benchmark=benchmark_range,
                triggered_by=keyword_hit,
                recommendation="Measure supplier lead time CV first. Only reduce safety stock if CV < 0.15.",
            )

        if kpi_id == "supplier_lead_time" and direction == "decrease" and pct_change and pct_change > 40:
            return KPIWarning(
                kpi_id=kpi_id,
                kpi_name=kpi_name,
                severity="AMBER",
                message=(
                    f"Lead time reduction of {pct_change:.0f}% is ambitious. "
                    f"Industry ideal for {self.industry}: {benchmark_range.get('ideal', 'N/A')} days. "
                    "Aggressive lead time targets often require supplier investment that is not pre-agreed."
                ),
                benchmark=benchmark_range,
                triggered_by=keyword_hit,
                recommendation="Confirm supplier capability and contractual commitment before setting >40% lead time reduction targets.",
            )

        if kpi_id == "forecast_accuracy" and direction == "increase" and pct_change and pct_change > 20:
            return KPIWarning(
                kpi_id=kpi_id,
                kpi_name=kpi_name,
                severity="AMBER",
                message=(
                    f"Forecast accuracy improvement of {pct_change:.0f}% in a single initiative is rarely achievable. "
                    f"Industry ideal for {self.industry}: {benchmark_range.get('ideal', 'N/A')}%. "
                    "Validate the baseline MAPE and ensure clean historical data exists."
                ),
                benchmark=benchmark_range,
                triggered_by=keyword_hit,
                recommendation=f"Set realistic target: +8-12% accuracy improvement in year 1. Validate that clean demand history (≥2 years) exists.",
            )

        if kpi_id == "cash_to_cash_cycle" and direction == "increase":
            return KPIWarning(
                kpi_id=kpi_id,
                kpi_name=kpi_name,
                severity="RED",
                message=(
                    "This recommendation appears to lengthen the Cash-to-Cash cycle. "
                    "Any C2C increase requires explicit working capital justification approved by Finance."
                ),
                benchmark=benchmark_range,
                triggered_by=keyword_hit,
                recommendation="Model full C2C impact (DIO + DSO + DPO changes) and get CFO-level sign-off before proceeding.",
            )

        # Generic INFO warning for any KPI mention without specific red flag
        if red_flags and pct_change and pct_change > 25:
            return KPIWarning(
                kpi_id=kpi_id,
                kpi_name=kpi_name,
                severity="INFO",
                message=(
                    f"Recommendation mentions {kpi_name} ({keyword_hit}). "
                    f"Benchmark for {self.industry}: {benchmark_range.get('min', '?')}-"
                    f"{benchmark_range.get('max', '?')} {kpi_data.get('unit', '')} "
                    f"(ideal: {benchmark_range.get('ideal', '?')}). "
                    "Validate the proposed change stays within safe operating range."
                ),
                benchmark=benchmark_range,
                triggered_by=keyword_hit,
                recommendation=f"Ensure {kpi_name} remains in benchmark range after implementation.",
            )

        return None

    def get_benchmark_summary(self) -> Dict:
        """Return all benchmarks for the current industry as a summary."""
        summary = {}
        for kpi_id, kpi_data in self._benchmarks.get("kpis", {}).items():
            r = self._get_range(kpi_data)
            if r:
                summary[kpi_id] = {
                    "description": kpi_data.get("description", ""),
                    "unit": kpi_data.get("unit", ""),
                    "ideal": r.get("ideal"),
                    "safe_min": r.get("min"),
                    "safe_max": r.get("max"),
                    "direction": kpi_data.get("direction", "higher_is_better"),
                }
        return summary
