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
        for q in self.questions["questions"]:
            if q["id"] == qid:
                return q
        return None

    def _score_q1(self, answer_id: str) -> float:
        for opt in self._find_question("q1")["options"]:
            if opt["id"] == answer_id:
                return float(opt.get("score", 0))
        return 0.0

    def _score_q2(self, answer_id: str, domain: str) -> float:
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
        for opt in self._find_question("q3").get("options", []):
            if opt["id"] == answer_id:
                return float(opt.get("score", 0))
        return 0.0

    def _score_q4(self, answer_id: str) -> float:
        for opt in self._find_question("q4").get("options", []):
            if opt["id"] == answer_id:
                return float(opt.get("score", 0))
        return 0.0

    def _score_q5(self, q5_answers: Dict) -> tuple:
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
