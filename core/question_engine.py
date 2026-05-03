"""
Product Skout — Adaptive Question Engine
Reads questions.yaml and drives the branching question flow.
LLM-agnostic, fully config-driven.
"""
from __future__ import annotations
import yaml
from pathlib import Path
from typing import Any, Dict, List, Optional


# Q3 stakeholder ordering per domain — most relevant first
_Q3_DOMAIN_ORDER: Dict[str, List[str]] = {
    "planning":    ["sc_planners", "leadership", "operations", "finance", "procurement_mgrs", "external_partners"],
    "procurement": ["procurement_mgrs", "finance", "leadership", "sc_planners", "operations", "external_partners"],
    "repair":      ["operations", "sc_planners", "procurement_mgrs", "finance", "leadership", "external_partners"],
    "trade":       ["finance", "leadership", "procurement_mgrs", "operations", "sc_planners", "external_partners"],
    "fraud":       ["finance", "leadership", "procurement_mgrs", "operations", "sc_planners", "external_partners"],
}


class QuestionEngine:
    """
    Drives the 5-question adaptive flow for Product Skout.

    Usage:
        engine = QuestionEngine()
        engine.record_answer("origin", "user_reported")
        options = engine.get_options("q2")   # adapts based on q1 answer
    """

    QUESTION_ORDER = ["q1", "q2", "q3", "q4", "q5"]

    def __init__(self, config_path: str = "config/questions.yaml",
                 user_context_path: str = "config/user_context.yaml"):
        self.config = self._load(config_path)
        self.user_ctx = self._load(user_context_path)
        self.answers: Dict[str, Any] = {}

    # ------------------------------------------------------------------ #
    # Config loading
    # ------------------------------------------------------------------ #

    @staticmethod
    def _load(path: str) -> Dict:
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Config not found: {path}")
        with open(p, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    # ------------------------------------------------------------------ #
    # Question retrieval
    # ------------------------------------------------------------------ #

    def get_pre_question(self) -> Dict:
        """Returns the origin pre-question (multiplier source)."""
        return self.config["pre_question"]

    def get_question(self, question_id: str) -> Optional[Dict]:
        """Retrieve a question definition by ID."""
        for q in self.config["questions"]:
            if q["id"] == question_id:
                return q
        return None

    def get_options(self, question_id: str) -> List[Dict]:
        """
        Return options for a question, with:
        - Hidden options filtered out (Q1)
        - Q2 adaptive branching on Q1 domain answer
        - Q3 reordered by domain relevance
        """
        q = self.get_question(question_id)
        if not q:
            return []

        if not q.get("adaptive", False):
            options = self._inject_custom(question_id, q.get("options", []))
            # Filter hidden options (e.g. WIP domains kept in config but hidden in UI)
            options = [o for o in options if not o.get("hidden", False)]
            # Domain-aware Q3 ordering
            if question_id == "q3":
                options = self._order_q3_by_domain(options)
            return options

        # Adaptive questions (Q2 branches on Q1)
        adaptive_field = q.get("adaptive_field")
        parent_answer  = self.answers.get(adaptive_field)

        if question_id == "q2":
            domain_opts = q.get("domain_options", {})
            if parent_answer and parent_answer in domain_opts:
                return domain_opts[parent_answer]
            return q.get("default_options", [])

        return q.get("default_options", q.get("options", []))

    def _inject_custom(self, question_id: str, base_options: List[Dict]) -> List[Dict]:
        """
        Merge user-defined custom domains into Q1 options.
        Custom domains defined in user_context.yaml appear after built-ins.
        """
        if question_id != "q1":
            return base_options

        custom_domains = (
            self.user_ctx.get("custom_extensions", {}).get("domains", []) or []
        )
        if not custom_domains:
            return base_options

        extras = [
            {
                "id":          d["id"],
                "label":       d.get("label", d["id"]),
                "icon":        "🔧",
                "description": d.get("description", ""),
                "score":       9,
                "wip":         False,
                "hidden":      False,
                "custom":      True,
            }
            for d in custom_domains
        ]
        return base_options + extras

    def _order_q3_by_domain(self, options: List[Dict]) -> List[Dict]:
        """Reorder Q3 stakeholder options so the most relevant role appears first."""
        domain = self.answers.get("q1", "")
        order = _Q3_DOMAIN_ORDER.get(domain)
        if not order:
            return options
        by_id = {o["id"]: o for o in options}
        ordered = [by_id[oid] for oid in order if oid in by_id]
        # Append any options not in the order map (e.g. custom)
        covered = set(order)
        ordered += [o for o in options if o["id"] not in covered]
        return ordered

    # ------------------------------------------------------------------ #
    # Answer recording
    # ------------------------------------------------------------------ #

    def record_answer(self, question_id: str, answer_id: str,
                      free_text: Optional[str] = None) -> None:
        """Record a single-select answer."""
        self.answers[question_id] = answer_id
        if free_text:
            self.answers[f"{question_id}_text"] = free_text

    def record_q5(self, frequency: str, severity: str,
                  workaround: str) -> None:
        """Record the multi-factor Q5 answer."""
        self.answers["q5"] = {
            "frequency":       frequency,
            "severity":        severity,
            "workaround_effort": workaround,
        }

    # ------------------------------------------------------------------ #
    # Derived helpers
    # ------------------------------------------------------------------ #

    def get_origin_multiplier(self) -> float:
        """Return the multiplier for the origin pre-question answer."""
        origin = self.answers.get("origin")
        if not origin:
            return 1.0
        for opt in self.config["pre_question"]["options"]:
            if opt["id"] == origin:
                return float(opt.get("multiplier", 1.0))
        return 1.0

    def is_wip_domain(self) -> bool:
        """True if the selected Q1 domain is marked WIP."""
        q1 = self.answers.get("q1")
        if not q1:
            return False
        for opt in self.get_question("q1")["options"]:
            if opt["id"] == q1:
                return bool(opt.get("wip", False))
        return False

    def is_complete(self) -> bool:
        """True when all 5 questions plus the origin have been answered."""
        required = {"origin", "q1", "q2", "q3", "q4", "q5"}
        return required.issubset(self.answers.keys())

    def get_label(self, question_id: str, answer_id: str) -> str:
        """Return the human-readable label for a given answer ID."""
        if question_id == "origin":
            for opt in self.config["pre_question"]["options"]:
                if opt["id"] == answer_id:
                    return opt.get("label", answer_id)
        else:
            for opt in self.get_options(question_id):
                if opt["id"] == answer_id:
                    return opt.get("label", answer_id)
        return answer_id

    def get_answered_summary(self) -> Dict[str, str]:
        """Return human-readable answers for all answered questions."""
        summary = {}
        for qid in ["origin", "q1", "q2", "q3", "q4"]:
            ans = self.answers.get(qid)
            if ans:
                summary[qid] = self.get_label(qid, ans)
        q5 = self.answers.get("q5")
        if q5 and isinstance(q5, dict):
            q5_q = self.get_question("q5")
            labels = {}
            for factor in q5_q.get("factors", []):
                fid = factor["id"]
                val = q5.get(fid)
                if val:
                    for opt in factor["options"]:
                        if opt["id"] == val:
                            labels[factor["label"]] = opt["label"]
            summary["q5"] = labels
        return summary

    def reset(self) -> None:
        """Clear all answers (start fresh)."""
        self.answers = {}
