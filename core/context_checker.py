"""
Skout — Pattern #7: Context Checker (Context Sensitivity)
==========================================================
Validates that enough context exists before allowing a PASS verdict.

If critical context is missing, the verdict returns "INSUFFICIENT_CONTEXT"
rather than passing by default. This prevents confident false positives
when the recommendation hasn't been grounded in the operating environment.

Required context tiers:
  - CRITICAL: Must be known. Absence blocks PASS.
  - IMPORTANT: Should be known. Absence triggers a CONDITIONAL (not a block).
  - HELPFUL: Nice to have. Absence noted but doesn't change verdict.

Usage:
    checker = ContextChecker()
    result = checker.check(context_dict)
    if not result.is_sufficient:
        print("Missing:", result.missing_critical)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any


# ------------------------------------------------------------------ #
# Context schema — what we need to know before evaluating safely
# ------------------------------------------------------------------ #

CONTEXT_SCHEMA = {
    "industry": {
        "tier": "CRITICAL",
        "question": "What industry vertical is this supply chain in?",
        "hint": "e.g. retail, automotive, pharma, food & beverage, electronics",
        "why": "KPI benchmarks, lead times, and resilience norms differ significantly by industry.",
        "valid_values": ["retail", "automotive", "pharma", "food_beverage", "electronics", "industrial", "other"],
    },
    "demand_pattern": {
        "tier": "CRITICAL",
        "question": "What is the demand pattern for this product/category?",
        "hint": "stable, seasonal, lumpy, new product, or event-driven",
        "why": "Safety stock, forecast method, and inventory policy must be matched to demand pattern.",
        "valid_values": ["stable", "seasonal", "lumpy", "new_product", "event_driven"],
    },
    "supply_chain_maturity": {
        "tier": "IMPORTANT",
        "question": "What is the organisation's supply chain maturity level?",
        "hint": "reactive (firefighting), defined (processes exist), optimised (data-driven), or adaptive (predictive)",
        "why": "Advanced solutions (ML forecasting, supplier collaboration) fail in low-maturity environments.",
        "valid_values": ["reactive", "defined", "optimised", "adaptive"],
    },
    "disruption_environment": {
        "tier": "IMPORTANT",
        "question": "What is the current supply chain disruption environment?",
        "hint": "stable (normal operations), elevated (some disruptions), volatile (frequent disruptions), crisis (major active disruption)",
        "why": "Lean/JIT approaches are dangerous in volatile or crisis environments.",
        "valid_values": ["stable", "elevated", "volatile", "crisis"],
    },
    "planning_horizon": {
        "tier": "HELPFUL",
        "question": "What is the planning horizon for this recommendation?",
        "hint": "tactical (0-3 months), operational (3-12 months), strategic (1-3 years)",
        "valid_values": ["tactical", "operational", "strategic"],
        "why": "Short-horizon recommendations shouldn't promise long-term structural improvements.",
    },
    "data_availability": {
        "tier": "HELPFUL",
        "question": "What data systems and quality are available?",
        "hint": "e.g. ERP with clean data, manual spreadsheets, patchy history, no system",
        "valid_values": ["erp_clean", "erp_patchy", "spreadsheets", "manual", "none"],
        "why": "Data-driven recommendations fail without clean data. ML fails without 2+ years history.",
    },
}

# High-risk combinations that override verdict even if context is present
HIGH_RISK_COMBOS = [
    {
        "conditions": {"demand_pattern": "lumpy", "disruption_environment": "volatile"},
        "block_patterns": ["reduce safety stock", "just-in-time", "lean inventory", "cut buffer"],
        "message": "JIT/lean approaches are extremely high-risk when demand is lumpy AND disruptions are volatile.",
    },
    {
        "conditions": {"supply_chain_maturity": "reactive"},
        "block_patterns": ["ml forecast", "ai", "machine learning", "advanced analytics", "predictive"],
        "message": "Advanced analytics solutions typically fail in reactive-maturity organisations without data infrastructure.",
    },
    {
        "conditions": {"disruption_environment": "crisis"},
        "block_patterns": ["reduce supplier", "consolidate supplier", "sole source", "single source"],
        "message": "Supplier consolidation is extremely dangerous during an active supply crisis.",
    },
]


# ------------------------------------------------------------------ #
# Result dataclass
# ------------------------------------------------------------------ #

@dataclass
class ContextCheckResult:
    is_sufficient: bool
    missing_critical: List[str] = field(default_factory=list)
    missing_important: List[str] = field(default_factory=list)
    missing_helpful: List[str] = field(default_factory=list)
    risk_combo_warnings: List[str] = field(default_factory=list)
    questions_to_ask: List[Dict] = field(default_factory=list)
    verdict: str = "SUFFICIENT"   # SUFFICIENT / CONDITIONAL / INSUFFICIENT
    completeness_pct: int = 0

    @property
    def verdict_emoji(self) -> str:
        return {"SUFFICIENT": "✅", "CONDITIONAL": "⚠️", "INSUFFICIENT": "🔴"}.get(self.verdict, "❓")

    def to_dict(self) -> Dict:
        return {
            "is_sufficient": self.is_sufficient,
            "missing_critical": self.missing_critical,
            "missing_important": self.missing_important,
            "missing_helpful": self.missing_helpful,
            "risk_combo_warnings": self.risk_combo_warnings,
            "questions_to_ask": self.questions_to_ask,
            "verdict": self.verdict,
            "verdict_emoji": self.verdict_emoji,
            "completeness_pct": self.completeness_pct,
        }


# ------------------------------------------------------------------ #
# Context Checker
# ------------------------------------------------------------------ #

class ContextChecker:
    """
    Validates whether sufficient context exists to safely evaluate a recommendation.
    """

    def check(
        self,
        context: Dict[str, Any],
        recommendation_text: str = "",
    ) -> ContextCheckResult:
        """
        Check if context is sufficient for safe evaluation.

        Args:
            context: Dict with keys matching CONTEXT_SCHEMA (e.g. industry, demand_pattern).
            recommendation_text: Optional recommendation text for combo risk checks.

        Returns:
            ContextCheckResult with completeness assessment and questions to ask.
        """
        missing_critical: List[str] = []
        missing_important: List[str] = []
        missing_helpful: List[str] = []
        questions: List[Dict] = []

        total_fields = len(CONTEXT_SCHEMA)
        filled_fields = 0

        for field_id, schema in CONTEXT_SCHEMA.items():
            value = context.get(field_id)
            is_present = value is not None and str(value).strip() not in ("", "unknown", "not_specified")

            if is_present:
                filled_fields += 1
            else:
                q = {
                    "field": field_id,
                    "question": schema["question"],
                    "hint": schema.get("hint", ""),
                    "why": schema.get("why", ""),
                    "tier": schema["tier"],
                    "options": schema.get("valid_values", []),
                }
                questions.append(q)

                if schema["tier"] == "CRITICAL":
                    missing_critical.append(field_id)
                elif schema["tier"] == "IMPORTANT":
                    missing_important.append(field_id)
                else:
                    missing_helpful.append(field_id)

        # Check high-risk context combinations
        risk_combo_warnings: List[str] = []
        if recommendation_text:
            rec_lower = recommendation_text.lower()
            for combo in HIGH_RISK_COMBOS:
                conditions_met = all(
                    context.get(k) == v
                    for k, v in combo["conditions"].items()
                )
                if conditions_met:
                    patterns_present = any(p in rec_lower for p in combo["block_patterns"])
                    if patterns_present:
                        risk_combo_warnings.append(combo["message"])

        # Determine verdict
        if missing_critical:
            verdict = "INSUFFICIENT"
            is_sufficient = False
        elif missing_important or risk_combo_warnings:
            verdict = "CONDITIONAL"
            is_sufficient = True  # Can evaluate, but with caveats
        else:
            verdict = "SUFFICIENT"
            is_sufficient = True

        completeness_pct = int((filled_fields / total_fields) * 100)

        return ContextCheckResult(
            is_sufficient=is_sufficient,
            missing_critical=missing_critical,
            missing_important=missing_important,
            missing_helpful=missing_helpful,
            risk_combo_warnings=risk_combo_warnings,
            questions_to_ask=questions,
            verdict=verdict,
            completeness_pct=completeness_pct,
        )

    def build_context_from_skout_answers(
        self,
        answers: Dict[str, Any],
        user_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Build a context dict from Skout's Q1-Q5 answers and user_context.yaml.
        Bridges existing Skout data into the context checker format.
        """
        ctx: Dict[str, Any] = {}
        uc = user_context or {}

        # Map domain → SCOR category (already well-defined in scoring_engine)
        domain_map = {
            "planning": "planning",
            "procurement": "sourcing",
            "repair": "return",
            "trade": "deliver",
            "fraud": "enable",
        }
        domain = answers.get("q1", "")
        if domain:
            ctx["scor_domain"] = domain_map.get(domain, domain)

        # Industry from user context
        org_type = uc.get("organization", {}).get("type", "")
        if org_type:
            ctx["industry"] = org_type

        # Demand pattern — not in current Skout questions, will be missing
        # (that's intentional — it will show up as a gap to fill)

        # Company maturity — can proxy from user_context
        maturity = uc.get("supply_chain_maturity", {})
        if maturity:
            ctx["supply_chain_maturity"] = maturity

        return ctx

    @staticmethod
    def format_questions_for_ui(questions: List[Dict]) -> List[Dict]:
        """Format questions in a Streamlit-friendly structure."""
        return [
            {
                "label": f"{'🔴' if q['tier'] == 'CRITICAL' else '🟡' if q['tier'] == 'IMPORTANT' else '🔵'} {q['question']}",
                "field": q["field"],
                "hint": q["hint"],
                "why": q["why"],
                "options": q["options"],
                "tier": q["tier"],
            }
            for q in questions
        ]
