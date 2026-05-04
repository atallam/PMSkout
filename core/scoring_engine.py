"""
Skout — Scoring Engine
Computes the verdict score from question answers.
Fully rule-based — no LLM dependency.
"""
from __future__ import annotations
import yaml
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple


# ------------------------------------------------------------------ #
# SCOR Framework alignment mapping
# Source: APICS SCOR model (Plan / Source / Make / Deliver / Return / Enable)
# ------------------------------------------------------------------ #

_SCOR_DOMAIN: Dict[str, str] = {
    "planning":    "Plan",
    "procurement": "Source",
    "repair":      "Return",
    "trade":       "Deliver",
    "fraud":       "Enable",
}

_SCOR_PROBLEM: Dict[str, str] = {
    "planning__forecast_accuracy":         "Plan",
    "planning__inventory_optimization":    "Plan",
    "planning__sop_process":               "Plan",
    "planning__demand_sensing":            "Plan",
    "planning__capacity_planning":         "Plan",
    "procurement__supplier_risk":          "Source",
    "procurement__invoice_reconciliation": "Source",
    "procurement__contract_compliance":    "Source",
    "procurement__po_cycle_time":          "Source",
    "procurement__tail_spend":             "Source",
    "repair__turnaround_time":             "Return",
    "repair__parts_availability":          "Return",
    "repair__warranty_claims":             "Return",
    "repair__cost_per_repair":             "Return",
    "repair__counterfeit_parts":           "Return",
    "repair__reverse_logistics":           "Return",
    "trade__customs_delays":               "Deliver",
    "trade__duty_optimization":            "Deliver",
    "trade__compliance_risk":              "Enable",
    "trade__trade_partner":                "Source",
    "fraud__invoice_fraud":                "Enable",
    "fraud__supplier_collusion":           "Source",
    "fraud__internal_controls":            "Enable",
    "fraud__warranty_fraud":               "Return",
}

_SCOR_ICONS: Dict[str, str] = {
    "Plan":    "📋",
    "Source":  "🛒",
    "Make":    "🏭",
    "Deliver": "🚚",
    "Return":  "↩️",
    "Enable":  "⚙️",
}

_SCOR_DESCRIPTIONS: Dict[str, str] = {
    "Plan":    "Demand, S&OP, inventory planning and capacity balancing",
    "Source":  "Supplier selection, procurement, contract management, and spend control",
    "Make":    "Production, assembly, and manufacturing operations",
    "Deliver": "Order management, logistics, trade compliance, and customs",
    "Return":  "Reverse logistics, repairs, warranty, MRO, and returns management",
    "Enable":  "Cross-process risk management, controls, fraud detection, and compliance governance",
}


@dataclass
class VerdictResult:
    """
    Immutable result object returned by ScoringEngine.compute().

    Attributes:
        base_score:         Raw sum of dimension scores before origin multiplier.
        final_score:        base_score × origin_multiplier, capped at 100.
        origin_multiplier:  Multiplier derived from the idea's source (Q0).
        band:               Machine-readable verdict band id (e.g. "high_priority").
        band_label:         Human-readable band label (e.g. "High Priority").
        band_emoji:         Emoji for the band (e.g. "🟢").
        band_color:         Hex colour for the band used in UI.
        action:             Recommended PM action for this band.
        headline:           Short verdict headline for display.
        message:            Detailed verdict explanation.
        next_steps:         Ordered list of recommended next steps.
        dimension_scores:   Per-dimension raw scores {dimension_id: score}.
        dimension_max:      Max possible points per dimension from config.
        confidence_flags:   List of flag dicts {type, message} for warnings.
        is_wip_domain:      True if the selected domain is marked WIP in config.
        deep_dive_unlocked: True if final_score ≥ deep_think_threshold.
        deep_think_threshold: Minimum score to unlock Research Plan (default 80).
        scor_category:      SCOR framework domain (Plan/Source/Make/Deliver/Return/Enable).
        scor_icon:          Emoji icon for the SCOR category.
        scor_description:   One-line description of the SCOR category.
        wsjf_score:         Weighted Shortest Job First urgency score (0–10).
        opportunity_gap:    Ulwick ODI opportunity gap score (0–20).
    """
    base_score: float
    final_score: float
    origin_multiplier: float
    band: str
    band_label: str
    band_emoji: str
    band_color: str
    action: str
    headline: str
    message: str
    next_steps: List[str]
    dimension_scores: Dict[str, float]
    dimension_max: Dict[str, int]
    confidence_flags: List[Dict]
    is_wip_domain: bool
    deep_dive_unlocked: bool
    deep_think_threshold: int = 80
    scor_category: str = ""
    scor_icon: str = ""
    scor_description: str = ""
    wsjf_score: float = 0.0
    opportunity_gap: float = 0.0

    @property
    def percent(self) -> int:
        return int(self.final_score)

    @property
    def q5_factor_scores(self) -> Dict[str, int]:
        return getattr(self, "_q5_factors", {})


    def to_dict(self) -> Dict:
        """Serialize to a plain JSON-safe dict for persistence."""
        return {
            "base_score":          self.base_score,
            "final_score":         self.final_score,
            "origin_multiplier":   self.origin_multiplier,
            "band":                self.band,
            "band_label":          self.band_label,
            "band_emoji":          self.band_emoji,
            "band_color":          self.band_color,
            "action":              self.action,
            "headline":            self.headline,
            "message":             self.message,
            "next_steps":          list(self.next_steps),
            "dimension_scores":    dict(self.dimension_scores),
            "dimension_max":       dict(self.dimension_max),
            "confidence_flags":    list(self.confidence_flags),
            "is_wip_domain":       self.is_wip_domain,
            "deep_dive_unlocked":  self.deep_dive_unlocked,
            "deep_think_threshold": self.deep_think_threshold,
            "scor_category":       self.scor_category,
            "scor_icon":           self.scor_icon,
            "scor_description":    self.scor_description,
            "wsjf_score":          self.wsjf_score,
            "opportunity_gap":     self.opportunity_gap,
            "q5_factors":          self.q5_factor_scores,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "VerdictResult":
        """Reconstruct a VerdictResult from a persisted dict."""
        obj = cls(
            base_score=float(d.get("base_score", 0)),
            final_score=float(d.get("final_score", 0)),
            origin_multiplier=float(d.get("origin_multiplier", 1.0)),
            band=d.get("band", ""),
            band_label=d.get("band_label", ""),
            band_emoji=d.get("band_emoji", ""),
            band_color=d.get("band_color", "#6b7280"),
            action=d.get("action", ""),
            headline=d.get("headline", ""),
            message=d.get("message", ""),
            next_steps=list(d.get("next_steps", [])),
            dimension_scores={k: float(v) for k, v in d.get("dimension_scores", {}).items()},
            dimension_max={k: int(v) for k, v in d.get("dimension_max", {}).items()},
            confidence_flags=list(d.get("confidence_flags", [])),
            is_wip_domain=bool(d.get("is_wip_domain", False)),
            deep_dive_unlocked=bool(d.get("deep_dive_unlocked", False)),
            deep_think_threshold=int(d.get("deep_think_threshold", 80)),
            scor_category=d.get("scor_category", ""),
            scor_icon=d.get("scor_icon", ""),
            scor_description=d.get("scor_description", ""),
            wsjf_score=float(d.get("wsjf_score", 0.0)),
            opportunity_gap=float(d.get("opportunity_gap", 0.0)),
        )
        obj._q5_factors = dict(d.get("q5_factors", {}))
        return obj


class ScoringEngine:
    """Computes verdict score from QuestionEngine answers."""

    def __init__(
        self,
        scoring_config: str = "config/scoring.yaml",
        questions_config: str = "config/questions.yaml",
        user_context: str = "config/user_context.yaml",
    ):
        self.scoring = self._load(scoring_config)
        self.questions = self._load(questions_config)
        self.user_ctx = self._load(user_context)

    @staticmethod
    def _load(path: str) -> Dict:
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Config not found: {path}")
        with open(p, encoding="utf-8") as f:
            return yaml.safe_load(f)

    def _find_question(self, qid: str) -> Optional[Dict]:
        """Look up a question definition by its id string."""
        for q in self.questions["questions"]:
            if q["id"] == qid:
                return q
        return None

    def _score_q1(self, answer_id: str) -> float:
        """Return the domain-fit score for the Q1 (domain) answer."""
        for opt in self._find_question("q1")["options"]:
            if opt["id"] == answer_id:
                return float(opt.get("score", 0))
        return 0.0

    def _score_q2(self, answer_id: str, domain: str) -> float:
        """
        Return the problem-clarity score for Q2, capped at 25.
        Uses domain-specific options first; falls back to default_options.
        """
        q2 = self._find_question("q2")
        domain_opts = q2.get("domain_options", {}).get(domain, [])
        for opt in domain_opts:
            if opt["id"] == answer_id:
                return min(25.0, float(opt.get("score", 0)))
        for opt in q2.get("default_options", []):
            if opt["id"] == answer_id:
                return min(25.0, float(opt.get("score", 0)))
        return 0.0

    def _score_q3(self, answer_id: str) -> float:
        """Return the stakeholder-reach score for the Q3 answer."""
        for opt in self._find_question("q3").get("options", []):
            if opt["id"] == answer_id:
                return float(opt.get("score", 0))
        return 0.0

    def _score_q4(self, answer_id: str) -> float:
        """Return the market-gap score for the Q4 (current state) answer."""
        for opt in self._find_question("q4").get("options", []):
            if opt["id"] == answer_id:
                return float(opt.get("score", 0))
        return 0.0

    def _score_q5(self, q5_answers: Dict) -> tuple:
        """
        Score the three Q5 factors (frequency, severity, workaround_effort).
        Returns (total_score capped at 30, {factor_id: pts} dict).
        """
        if not q5_answers:
            return 0.0, {}
        q5 = self._find_question("q5")
        factor_scores: Dict[str, int] = {}
        total = 0.0
        for factor in q5.get("factors", []):
            fid = factor["id"]
            answer_id = q5_answers.get(fid)
            for opt in factor.get("options", []):
                if opt["id"] == answer_id:
                    pts = int(opt.get("score", 0))
                    factor_scores[fid] = pts
                    total += pts
                    break
        return min(30.0, total), factor_scores

    def _get_weights(self) -> Dict[str, float]:
        """
        Return per-dimension weight multipliers.
        At Phase 2+ the user may supply custom weights in user_context.yaml;
        otherwise every dimension gets a multiplier of 1.0 (no adjustment).
        """
        custom = self.user_ctx.get("scoring_customization", {})
        if custom.get("enabled") and custom.get("weights"):
            w = custom["weights"]
            dims = self.scoring["dimensions"]
            result = {}
            for dim, cfg in dims.items():
                user_w = w.get(dim, cfg["max_points"])
                result[dim] = user_w / cfg["max_points"]
            return result
        return {dim: 1.0 for dim in self.scoring["dimensions"]}

    def _check_flags(self, answers, base_score, is_wip, q5_factors) -> List[Dict]:
        """
        Build confidence-flag list from scoring config rules.

        Flags produced:
          - "warning"  if origin has low external validation but score is high.
          - "info"     if the selected domain is marked WIP.
          - "caution"  if any single Q5 factor has a minimum score (score=1).

        Returns list of {type, message} dicts (messages with empty text filtered out).
        """
        flags = []
        flag_cfg = self.scoring.get("confidence_flags", {})
        origin = answers.get("origin", "")
        low_val_origins = flag_cfg.get("high_score_low_validation", {}).get("condition_origin", [])
        threshold = flag_cfg.get("high_score_low_validation", {}).get("score_threshold", 70)
        if origin in low_val_origins and base_score > threshold:
            flags.append({"type": "warning", "message": flag_cfg["high_score_low_validation"]["message"]})
        if is_wip:
            flags.append({"type": "info", "message": flag_cfg.get("wip_domain", {}).get("message", "")})
        if q5_factors and any(v == 1 for v in q5_factors.values()):
            flags.append({"type": "caution", "message": flag_cfg.get("single_low_factor", {}).get("message", "")})
        return [f for f in flags if f.get("message")]

    # Phase 2 supplemental metrics ------------------------------------ #

    def _get_scor(self, domain: str, problem_id: str) -> Tuple[str, str, str]:
        key = f"{domain}__{problem_id}" if problem_id else ""
        category = _SCOR_PROBLEM.get(key) or _SCOR_DOMAIN.get(domain, "Enable")
        return category, _SCOR_ICONS.get(category, "⚙️"), _SCOR_DESCRIPTIONS.get(category, "")

    def _compute_wsjf(self, dim_scores: Dict[str, float], q4: str, q5_factors: Dict[str, int]) -> float:
        # CoD = weighted blend of business_impact + stakeholder_reach
        bi  = dim_scores.get("business_impact",   0.0)
        sr  = dim_scores.get("stakeholder_reach",  0.0)
        cod = (bi / 30.0) * 0.6 + (sr / 15.0) * 0.4
        duration_map = {
            "manual_spreadsheet": 4, "not_handled": 4,
            "legacy_erp": 3, "siloed_tools": 2,
            "internal_tool": 2, "competitor_exists": 1,
        }
        duration = duration_map.get(q4, 3)
        raw = cod / (duration / 4.0)
        return round(min(10.0, raw * 10), 1)

    def _compute_opportunity_gap(self, dim_scores: Dict[str, float]) -> float:
        # Ulwick ODI: Importance + max(Importance - Satisfaction, 0)
        bi = dim_scores.get("business_impact",  0.0)
        sr = dim_scores.get("stakeholder_reach", 0.0)
        mg = dim_scores.get("market_gap",         0.0)
        importance   = ((sr / 15.0) + (bi / 30.0)) / 2.0 * 10.0
        satisfaction = (1.0 - mg / 20.0) * 10.0
        gap          = importance + max(importance - satisfaction, 0.0)
        return round(min(20.0, gap), 1)

    # Main compute ---------------------------------------------------- #

    def compute(self, answers: Dict[str, Any], origin_multiplier: float = 1.0, is_wip_domain: bool = False) -> VerdictResult:
        domain     = answers.get("q1", "")
        problem_id = answers.get("q2", "")
        q4         = answers.get("q4", "")
        weights    = self._get_weights()

        q5_answers = answers.get("q5", {})
        q5_raw, q5_factors = self._score_q5(q5_answers)

        dim_scores = {
            "domain_fit":        self._score_q1(domain)            * weights["domain_fit"],
            "problem_clarity":   self._score_q2(problem_id, domain) * weights["problem_clarity"],
            "stakeholder_reach": self._score_q3(answers.get("q3","")) * weights["stakeholder_reach"],
            "market_gap":        self._score_q4(q4)                * weights["market_gap"],
            "business_impact":   q5_raw                            * weights["business_impact"],
        }

        base_score  = sum(dim_scores.values())
        final_score = min(100.0, base_score * origin_multiplier)
        band_info   = self._get_band(final_score)
        flags       = self._check_flags(answers, base_score, is_wip_domain, q5_factors)

        dtt = (self.user_ctx.get("research_preferences", {}).get("deep_think_threshold", 80) or 80)

        scor_cat, scor_icon, scor_desc = self._get_scor(domain, problem_id)
        wsjf    = self._compute_wsjf(dim_scores, q4, q5_factors)
        opp_gap = self._compute_opportunity_gap(dim_scores)

        result = VerdictResult(
            base_score=round(base_score, 1),
            final_score=round(final_score, 1),
            origin_multiplier=origin_multiplier,
            band=band_info["id"],
            band_label=band_info["label"],
            band_emoji=band_info["emoji"],
            band_color=band_info.get("color", "#6b7280"),
            action=band_info["action"],
            headline=band_info["headline"],
            message=band_info["message"],
            next_steps=band_info.get("next_steps", []),
            dimension_scores={k: round(v, 1) for k, v in dim_scores.items()},
            dimension_max={k: v["max_points"] for k, v in self.scoring["dimensions"].items()},
            confidence_flags=flags,
            is_wip_domain=is_wip_domain,
            deep_dive_unlocked=final_score >= dtt,
            deep_think_threshold=int(dtt),
            scor_category=scor_cat,
            scor_icon=scor_icon,
            scor_description=scor_desc,
            wsjf_score=wsjf,
            opportunity_gap=opp_gap,
        )
        result._q5_factors = q5_factors
        return result

    def _get_band(self, score: float) -> Dict:
        for band_id, band in self.scoring["verdict_bands"].items():
            if band["min"] <= score <= band["max"]:
                return {"id": band_id, **band}
        return {
            "id": "not_ready", "label": "Not Ready", "emoji": "❌",
            "color": "#dc2626", "action": "reconsider_scope",
            "headline": "Score out of expected range.",
            "message": "Please re-check your answers.", "next_steps": [],
        }
