"""
Signal Ingester — Phase 4
Multi-source ingestion: CSV/ERP exports, Slack paste, Jira JSON.
Produces an IdeaSignal dict that pre-populates the idea title + description.
"""
from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ------------------------------------------------------------------ #
# Data model
# ------------------------------------------------------------------ #

@dataclass
class IdeaSignal:
    """Structured signal extracted from an external source."""
    source_type: str           # "csv_erp" | "slack" | "jira" | "text"
    raw_text: str              # original pasted / uploaded text
    suggested_title: str       # short title for the idea
    suggested_description: str # richer description for the idea
    detected_domain: str       # detected SC domain (planning/procurement/…)
    detected_problem: str      # detected problem type hint
    signals: List[str] = field(default_factory=list)   # bullet evidence
    metrics: List[Dict] = field(default_factory=list)  # {name, value, unit}
    confidence: str = "low"    # "low" | "medium" | "high"
    warnings: List[str] = field(default_factory=list)  # parsing warnings

    def to_dict(self) -> Dict:
        return {
            "source_type": self.source_type,
            "raw_text": self.raw_text[:500],
            "suggested_title": self.suggested_title,
            "suggested_description": self.suggested_description,
            "detected_domain": self.detected_domain,
            "detected_problem": self.detected_problem,
            "signals": self.signals,
            "metrics": self.metrics,
            "confidence": self.confidence,
            "warnings": self.warnings,
        }


# ------------------------------------------------------------------ #
# Domain / problem keyword maps
# ------------------------------------------------------------------ #

_DOMAIN_KEYWORDS: Dict[str, List[str]] = {
    "planning": [
        "forecast", "demand plan", "inventory", "replenishment", "s&op",
        "supply plan", "sku", "safety stock", "reorder", "mps", "mrp",
        "shortage", "overstock", "days of supply", "dos",
    ],
    "procurement": [
        "purchase order", "po ", "invoice", "supplier", "vendor", "rfq",
        "sourcing", "spend", "contract", "requisition", "procure", "buying",
        "price variance", "maverick", "payment", "3-way match",
    ],
    "repair": [
        "maintenance", "repair", "mro", "work order", "asset", "downtime",
        "technician", "spare part", "equipment", "cmms", "preventive",
        "corrective", "service request", "break fix", "field service",
    ],
    "trade": [
        "customs", "trade", "import", "export", "tariff", "duty", "compliance",
        "hs code", "gst", "vat", "incoterm", "freight", "clearance",
        "declaration", "sanction", "denied party",
    ],
    "fraud": [
        "fraud", "duplicate", "anomaly", "unusual", "suspicious", "mismatch",
        "overcharge", "overbill", "ghost", "fictitious", "alert", "flag",
        "audit", "discrepancy",
    ],
}

_PROBLEM_KEYWORDS: Dict[str, List[str]] = {
    "forecast_accuracy":     ["forecast accuracy", "forecast error", "mape", "bias", "demand variability"],
    "inventory_optimization":["inventory", "overstock", "stockout", "safety stock", "dos", "turn"],
    "invoice_reconciliation":["invoice", "3-way match", "reconcil", "payment", "price variance"],
    "supplier_onboarding":   ["supplier onboarding", "vendor setup", "new supplier", "supplier portal"],
    "po_cycle_time":         ["po cycle", "purchase order cycle", "approval time", "po creation"],
    "asset_utilization":     ["asset utilization", "uptime", "availability", "oee", "downtime"],
    "work_order_completion":  ["work order", "wo cycle", "completion rate", "overdue wo"],
    "data_quality":          ["data quality", "data accuracy", "master data", "data error", "data issue"],
    "compliance_tracking":   ["compliance", "customs", "tariff", "regulation", "trade compliance"],
    "spend_visibility":      ["spend visibility", "spend analysis", "maverick", "off-contract"],
}


# ------------------------------------------------------------------ #
# Detection helpers
# ------------------------------------------------------------------ #

def _detect_domain(text: str) -> str:
    """Return the most likely SC domain based on keyword frequency."""
    text_lower = text.lower()
    scores = {domain: 0 for domain in _DOMAIN_KEYWORDS}
    for domain, kws in _DOMAIN_KEYWORDS.items():
        for kw in kws:
            scores[domain] += text_lower.count(kw)
    best = max(scores, key=lambda d: scores[d])
    return best if scores[best] > 0 else "planning"


def _detect_problem(text: str) -> str:
    """Return a problem_id hint based on keyword frequency."""
    text_lower = text.lower()
    scores = {pid: 0 for pid in _PROBLEM_KEYWORDS}
    for pid, kws in _PROBLEM_KEYWORDS.items():
        for kw in kws:
            scores[pid] += text_lower.count(kw)
    best = max(scores, key=lambda p: scores[p])
    return best if scores[best] > 0 else "other"


def _extract_metrics(text: str) -> List[Dict]:
    """Extract number+unit patterns as metrics evidence."""
    pattern = re.compile(
        r"(\b[\w\s]{2,30}?\b)\s*[:=]\s*([\d,\.]+)\s*(%|days?|hrs?|hours?|min|k|m|\$|usd|eur|gbp|units?|orders?|skus?)?",
        re.IGNORECASE,
    )
    metrics = []
    for m in pattern.finditer(text):
        name  = m.group(1).strip()
        value = m.group(2).replace(",", "")
        unit  = (m.group(3) or "").strip()
        if len(name) < 50 and len(metrics) < 10:
            metrics.append({"name": name, "value": value, "unit": unit})
    return metrics


# ------------------------------------------------------------------ #
# Source parsers
# ------------------------------------------------------------------ #

class SignalIngester:
    """
    Parses raw input from multiple sources and returns an IdeaSignal.

    Usage:
        ingester = SignalIngester()
        signal = ingester.from_slack(pasted_text)
        signal = ingester.from_csv(file_bytes)
        signal = ingester.from_jira(json_text)
        signal = ingester.from_text(raw_text)
    """

    # ---- Slack --------------------------------------------------------
    @staticmethod
    def from_slack(text: str) -> IdeaSignal:
        """
        Parse a block of pasted Slack messages.
        Extracts user complaints/requests as evidence signals.
        """
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        # Filter out timestamps and usernames (Slack format: "John Doe  10:32 AM")
        signal_lines: List[str] = []
        for line in lines:
            # Skip lines that look like headers/timestamps
            if re.match(r"^[\w\s]+\s+\d{1,2}:\d{2}\s*(AM|PM)?$", line):
                continue
            if len(line) > 20:
                signal_lines.append(line)

        domain  = _detect_domain(text)
        problem = _detect_problem(text)
        metrics = _extract_metrics(text)

        # Build suggested description from top signals
        top_signals = signal_lines[:5]
        description = (
            "User signal from Slack: team members are reporting "
            + (top_signals[0][:200] if top_signals else "an unspecified issue")
            + ". Additional context: "
            + "; ".join(s[:100] for s in top_signals[1:3])
        ) if top_signals else text[:300]

        # Guess a title from first meaningful line
        title_candidate = signal_lines[0][:60] if signal_lines else "Signal from Slack"
        title = re.sub(r"^\W+", "", title_candidate).strip()

        confidence = "high" if len(signal_lines) >= 5 else ("medium" if len(signal_lines) >= 2 else "low")

        return IdeaSignal(
            source_type="slack",
            raw_text=text,
            suggested_title=title,
            suggested_description=description,
            detected_domain=domain,
            detected_problem=problem,
            signals=top_signals[:8],
            metrics=metrics,
            confidence=confidence,
        )

    # ---- Jira ---------------------------------------------------------
    @staticmethod
    def from_jira(json_text: str) -> IdeaSignal:
        """
        Parse a Jira issue export (JSON or plain text).
        Supports both single-issue dict and issues[] array.
        """
        warnings: List[str] = []
        issues: List[Dict] = []

        try:
            data = json.loads(json_text)
            if isinstance(data, dict) and "issues" in data:
                issues = data["issues"]
            elif isinstance(data, dict) and "summary" in data:
                issues = [data]
            elif isinstance(data, list):
                issues = data
            else:
                issues = [data]
        except json.JSONDecodeError:
            # Fall back to text parsing
            warnings.append("Could not parse as JSON — treating as plain text.")
            return SignalIngester.from_text(json_text)

        if not issues:
            warnings.append("No issues found in Jira export.")
            return IdeaSignal(
                source_type="jira", raw_text=json_text,
                suggested_title="Jira Import", suggested_description="",
                detected_domain="planning", detected_problem="other",
                warnings=warnings,
            )

        all_text = " ".join(
            str(iss.get("summary", "")) + " " +
            str(iss.get("description", "")) + " " +
            str(iss.get("fields", {}).get("summary", "")) + " " +
            str(iss.get("fields", {}).get("description", ""))
            for iss in issues
        )

        domain  = _detect_domain(all_text)
        problem = _detect_problem(all_text)
        metrics = _extract_metrics(all_text)

        # Build signals from issue summaries
        signals = []
        for iss in issues[:8]:
            fields  = iss.get("fields", iss)
            summary = fields.get("summary", iss.get("summary", ""))
            if summary:
                signals.append(summary[:150])

        title_raw = issues[0].get("fields", issues[0]).get("summary", "Jira Signal")
        title = (str(title_raw) or "Jira Signal")[:60]

        description = (
            f"{len(issues)} Jira issue(s) highlight: "
            + "; ".join(signals[:3])
        )

        return IdeaSignal(
            source_type="jira",
            raw_text=json_text[:2000],
            suggested_title=title,
            suggested_description=description,
            detected_domain=domain,
            detected_problem=problem,
            signals=signals,
            metrics=metrics,
            confidence="high" if len(issues) >= 3 else "medium",
            warnings=warnings,
        )

    # ---- CSV / ERP export ---------------------------------------------
    @staticmethod
    def from_csv(file_bytes: bytes, filename: str = "export.csv") -> IdeaSignal:
        """
        Parse a CSV or text ERP export.
        Looks for metric columns and aggregates them into signals.
        """
        warnings: List[str] = []
        try:
            text = file_bytes.decode("utf-8", errors="replace")
        except Exception:
            text = ""
            warnings.append("Could not decode file.")

        reader = csv.DictReader(io.StringIO(text))
        rows = []
        try:
            for i, row in enumerate(reader):
                rows.append(row)
                if i >= 200:  # sample first 200 rows
                    break
        except Exception as e:
            warnings.append(f"CSV parse error: {e}")

        if not rows:
            return SignalIngester.from_text(text or filename)

        # Reconstruct full text for domain detection
        all_text = " ".join(
            " ".join(str(v) for v in row.values()) for row in rows[:50]
        )
        domain  = _detect_domain(all_text + " " + filename)
        problem = _detect_problem(all_text + " " + filename)

        # Build signals: numeric column summaries
        signals: List[str] = []
        numeric_cols: Dict[str, List[float]] = {}
        for row in rows:
            for col, val in row.items():
                try:
                    num = float(str(val).replace(",", "").replace("%", ""))
                    numeric_cols.setdefault(col, []).append(num)
                except (ValueError, TypeError):
                    pass

        for col, vals in list(numeric_cols.items())[:8]:
            if vals:
                avg  = sum(vals) / len(vals)
                minv = min(vals)
                maxv = max(vals)
                signals.append(f"{col}: avg={avg:.1f}, min={minv:.1f}, max={maxv:.1f} ({len(vals)} records)")

        metrics = [
            {"name": col, "value": f"{sum(v)/len(v):.2f}", "unit": "avg"}
            for col, v in list(numeric_cols.items())[:6] if v
        ]

        n_rows = len(rows)
        title = f"ERP signal: {filename.replace('.csv','').replace('_',' ')[:50]}"
        description = (
            f"{n_rows}+ rows from {filename}. Key metrics: "
            + "; ".join(signals[:3])
        )

        return IdeaSignal(
            source_type="csv_erp",
            raw_text=text[:2000],
            suggested_title=title,
            suggested_description=description,
            detected_domain=domain,
            detected_problem=problem,
            signals=signals[:8],
            metrics=metrics,
            confidence="high" if n_rows >= 10 else "medium",
            warnings=warnings,
        )

    # ---- Plain text (fallback) ----------------------------------------
    @staticmethod
    def from_text(text: str) -> IdeaSignal:
        """
        Generic text ingestion — user paste from any source.
        """
        lines = [l.strip() for l in text.splitlines() if len(l.strip()) > 20]
        domain  = _detect_domain(text)
        problem = _detect_problem(text)
        metrics = _extract_metrics(text)

        signals = lines[:8]
        title   = lines[0][:60] if lines else text[:60]
        desc    = text[:500]

        return IdeaSignal(
            source_type="text",
            raw_text=text,
            suggested_title=title.strip(),
            suggested_description=desc,
            detected_domain=domain,
            detected_problem=problem,
            signals=signals,
            metrics=metrics,
            confidence="medium" if len(lines) >= 3 else "low",
        )

    # ---- Auto-detect --------------------------------------------------
    @staticmethod
    def auto_detect(text: str, filename: Optional[str] = None) -> IdeaSignal:
        """
        Attempt to auto-detect the source type and parse accordingly.
        """
        stripped = text.strip()
        if stripped.startswith("{") or stripped.startswith("["):
            return SignalIngester.from_jira(stripped)
        # Slack heuristic: lines with colon-space and timestamp patterns
        if re.search(r"\b\d{1,2}:\d{2}\s*(AM|PM)\b", stripped, re.IGNORECASE):
            return SignalIngester.from_slack(stripped)
        return SignalIngester.from_text(stripped)
