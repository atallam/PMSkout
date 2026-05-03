"""
Skout — Domain Knowledge Engine (Master Orchestrator)
=======================================================
Runs all 7 domain knowledge patterns and returns a unified DomainAuditResult.

The 7 Patterns:
  #1  SCOR Framework Classifier  — which domain, what risks per domain
  #2  Challenger Agent           — devil's advocate failure mode surfacing
  #3  KPI Validator              — benchmark anchor validation
  #4  RAG Store                  — retrieves relevant domain knowledge
  #5  Adversarial Tests          — CI/pytest (not runtime)
  #6  Domain Scorer              — multi-dimensional weighted rubric
  #7  Context Checker            — validates enough context before passing

Overall verdict logic:
  PASS              — all dimensions pass, context sufficient, no critical challenges
  CONDITIONAL       — fixable issues: missing context, high (not critical) challenges
  BLOCK             — critical challenge, resilience below threshold, or insufficient context
  INSUFFICIENT_CONTEXT — critical context fields are missing

Usage:
    engine = DomainKnowledgeEngine(llm_provider=factory.get_provider())
    result = engine.evaluate(recommendation_text, context_dict)
    # result.overall_verdict in ("PASS", "CONDITIONAL", "BLOCK", "INSUFFICIENT_CONTEXT")
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .challenger_agent import ChallengerAgent, Challenge
from .kpi_validator import KPIValidator, KPIWarning
from .rag_store import RAGStore, KnowledgeChunk
from .domain_scorer import DomainScorer, DomainScoreResult
from .context_checker import ContextChecker, ContextCheckResult


# ------------------------------------------------------------------ #
# Result dataclass
# ------------------------------------------------------------------ #

@dataclass
class DomainAuditResult:
    """
    Unified result from all 7 domain knowledge patterns.

    Attributes:
        scor_domain:         SCOR domain identifier (e.g. "planning", "procurement").
        scor_risks:          Top-3 domain-specific risk statements from the SCOR library.
        challenges:          List of Challenge objects from the Challenger Agent (Pattern #2).
        challenger_summary:  Severity count summary dict from ChallengerAgent.summarise().
        kpi_warnings:        List of KPIWarning objects from the KPI Validator (Pattern #3).
        rag_chunks:          Most relevant KnowledgeChunk objects from RAG retrieval (Pattern #4).
        domain_score:        DomainScoreResult from the Domain Scorer (Pattern #6).
        context_check:       ContextCheckResult from the Context Checker (Pattern #7).
        overall_verdict:     Synthesised verdict: PASS / CONDITIONAL / BLOCK / INSUFFICIENT_CONTEXT.
        risk_level:          Aggregate risk level: LOW / MEDIUM / HIGH / CRITICAL.
        reasoning:           Human-readable explanation of the final verdict.
        action_items:        Concrete next steps derived from all pattern findings.
    """
    # Pattern #1 — SCOR classification
    scor_domain: str
    scor_risks: List[str]

    # Pattern #2 — Challenger agent
    challenges: List[Challenge]
    challenger_summary: Dict[str, Any]

    # Pattern #3 — KPI validator
    kpi_warnings: List[KPIWarning]

    # Pattern #4 — RAG context
    rag_chunks: List[KnowledgeChunk]

    # Pattern #6 — Domain scorer
    domain_score: DomainScoreResult

    # Pattern #7 — Context checker
    context_check: ContextCheckResult

    # Final verdict (synthesised from all patterns)
    overall_verdict: str       # PASS / CONDITIONAL / BLOCK / INSUFFICIENT_CONTEXT
    risk_level: str            # LOW / MEDIUM / HIGH / CRITICAL
    reasoning: str             # Human-readable explanation of the verdict
    action_items: List[str]    # Concrete next steps

    @property
    def verdict_emoji(self) -> str:
        """Emoji icon corresponding to overall_verdict (✅ PASS, ⚠️ CONDITIONAL, 🚫 BLOCK, ❓ INSUFFICIENT_CONTEXT)."""
        mapping = {
            "PASS": "✅",
            "CONDITIONAL": "⚠️",
            "BLOCK": "🚫",
            "INSUFFICIENT_CONTEXT": "❓",
        }
        return mapping.get(self.overall_verdict, "❓")

    @property
    def verdict_color(self) -> str:
        """Hex colour for the verdict badge in the Streamlit UI."""
        mapping = {
            "PASS": "#16a34a",
            "CONDITIONAL": "#ca8a04",
            "BLOCK": "#dc2626",
            "INSUFFICIENT_CONTEXT": "#7c3aed",
        }
        return mapping.get(self.overall_verdict, "#6b7280")

    @property
    def risk_color(self) -> str:
        """Hex colour for the risk-level badge: green → LOW, amber → MEDIUM, orange → HIGH, red → CRITICAL."""
        return {
            "LOW": "#16a34a",
            "MEDIUM": "#ca8a04",
            "HIGH": "#ea580c",
            "CRITICAL": "#dc2626",
        }.get(self.risk_level, "#6b7280")

    def to_dict(self) -> Dict:
        """Serialise all fields (including computed properties) to a plain dict for JSON export."""
        return {
            "scor_domain": self.scor_domain,
            "scor_risks": self.scor_risks,
            "challenges": [c.to_dict() for c in self.challenges],
            "challenger_summary": self.challenger_summary,
            "kpi_warnings": [w.to_dict() for w in self.kpi_warnings],
            "rag_chunks": [c.to_dict() for c in self.rag_chunks],
            "domain_score": self.domain_score.to_dict(),
            "context_check": self.context_check.to_dict(),
            "overall_verdict": self.overall_verdict,
            "verdict_emoji": self.verdict_emoji,
            "verdict_color": self.verdict_color,
            "risk_level": self.risk_level,
            "risk_color": self.risk_color,
            "reasoning": self.reasoning,
            "action_items": self.action_items,
        }


# ------------------------------------------------------------------ #
# SCOR risk index (Pattern #1 — enriched mapping)
# ------------------------------------------------------------------ #

_SCOR_DOMAIN_RISKS: Dict[str, List[str]] = {
    "planning": [
        "Forecast accuracy below 60% makes inventory optimisation unreliable",
        "S&OP improvements require cross-functional buy-in beyond technology",
        "Demand sensing requires clean, granular historical POS data",
    ],
    "procurement": [
        "Supplier consolidation below 3 qualified sources creates catastrophic risk",
        "Payment term extension beyond 90 days risks SME supplier financial distress",
        "Contract compliance improvements require ERP/CLM integration",
    ],
    "repair": [
        "Warranty fraud detection requires ≥2 years of labelled claim data",
        "Repair turnaround improvements require parts availability — don't optimise scheduling alone",
        "Reverse logistics is 5-10x more complex than forward logistics",
    ],
    "trade": [
        "Last-mile cost reduction often shifts cost to customer experience — validate NPS impact",
        "Customs compliance technology requires ongoing country-specific HS code maintenance",
        "Carrier consolidation below 2 alternatives per lane creates service disruption risk",
    ],
    "fraud": [
        "Fraud ML models require historical labelled data — validate this exists before committing",
        "Internal fraud detection must involve Legal and Compliance from day one",
        "Regulatory compliance timelines may override business prioritisation",
    ],
    "make": [
        "OEE improvements >15% in year 1 are rarely achievable without major capex",
        "Production scheduling optimisation requires real-time WIP visibility",
        "Quality control digitisation requires sensor/IoT infrastructure",
    ],
    "deliver": [
        "Warehouse automation ROI assumes consistent SKU mix — validate 3 years of volume data",
        "Cross-border compliance requires local legal review before implementation",
    ],
}

_DOMAIN_Q1_MAP = {
    "planning": "planning",
    "procurement": "procurement",
    "repair": "repair",
    "trade": "trade",
    "fraud": "fraud",
}


# ------------------------------------------------------------------ #
# Domain Knowledge Engine
# ------------------------------------------------------------------ #

class DomainKnowledgeEngine:
    """
    Master orchestrator for all 7 domain knowledge patterns.
    Runs patterns in sequence, synthesises results into a final audit.
    """

    def __init__(
        self,
        llm_provider=None,
        use_llm: bool = True,
        industry: str = "default",
    ):
        """
        Args:
            llm_provider: Optional BaseLLMProvider for LLM-enhanced patterns.
            use_llm: Enable LLM enrichment (disable for testing without API keys).
            industry: Supply chain industry for KPI benchmarking.
        """
        self.llm = llm_provider
        self.use_llm = use_llm and llm_provider is not None
        self.industry = industry

        # Initialise all pattern engines
        self.challenger = ChallengerAgent(llm_provider=llm_provider, use_llm=use_llm)
        self.kpi_validator = KPIValidator(industry=industry)
        self.rag_store = RAGStore()
        self.domain_scorer = DomainScorer(llm_provider=llm_provider if use_llm else None)
        self.context_checker = ContextChecker()

    # ---------------------------------------------------------------- #
    # Pattern #1 — SCOR classification
    # ---------------------------------------------------------------- #

    def _classify_scor(self, context: Dict) -> tuple[str, List[str]]:
        """Map Skout answers to SCOR domain and surface domain risks."""
        domain = context.get("scor_domain") or context.get("q1", "")
        mapped = _DOMAIN_Q1_MAP.get(domain, domain)
        risks = _SCOR_DOMAIN_RISKS.get(mapped, _SCOR_DOMAIN_RISKS.get(domain, []))
        return mapped or "unknown", risks[:3]  # Top 3 risks

    # ---------------------------------------------------------------- #
    # Verdict synthesis
    # ---------------------------------------------------------------- #

    def _synthesise_verdict(
        self,
        context_result: ContextCheckResult,
        challenger_summary: Dict,
        kpi_warnings: List[KPIWarning],
        domain_score: DomainScoreResult,
    ) -> tuple[str, str, str, List[str]]:
        """
        Combine all pattern results into an overall verdict.

        Returns:
            (overall_verdict, risk_level, reasoning, action_items)
        """
        action_items: List[str] = []
        reasons: List[str] = []

        # Pattern #7: Context check
        if context_result.verdict == "INSUFFICIENT":
            missing = ", ".join(context_result.missing_critical)
            return (
                "INSUFFICIENT_CONTEXT",
                "MEDIUM",
                f"Cannot evaluate safely — critical context is missing: {missing}. "
                "Provide this information before proceeding with evaluation.",
                [f"Answer: {f.replace('_', ' ').title()}" for f in context_result.missing_critical],
            )

        if context_result.risk_combo_warnings:
            for warning in context_result.risk_combo_warnings:
                reasons.append(f"Context risk: {warning}")
                action_items.append(f"Address context risk: {warning[:80]}")

        # Pattern #2: Challenger agent
        critical_count = challenger_summary.get("critical", 0)
        high_count = challenger_summary.get("high", 0)

        if critical_count > 0:
            reasons.append(f"{critical_count} CRITICAL failure pattern(s) detected")
            action_items.append("Resolve all CRITICAL challenges before re-evaluation")

        if high_count > 0:
            reasons.append(f"{high_count} HIGH severity risk(s) identified")
            action_items.append("Develop mitigation plan for all HIGH severity risks")

        # Pattern #3: KPI warnings
        red_kpi_warnings = [w for w in kpi_warnings if w.severity == "RED"]
        amber_kpi_warnings = [w for w in kpi_warnings if w.severity == "AMBER"]

        if red_kpi_warnings:
            for w in red_kpi_warnings:
                reasons.append(f"KPI red flag: {w.kpi_name}")
                action_items.append(w.recommendation)

        if amber_kpi_warnings:
            for w in amber_kpi_warnings:
                action_items.append(w.recommendation)

        # Pattern #6: Domain scorer verdict
        if domain_score.verdict == "BLOCK":
            reasons.append(f"Domain scorecard BLOCK: {domain_score.blocking_reason or 'Score too low'}")
            action_items.append("Redesign recommendation to improve resilience and service level dimensions")

        for tradeoff in domain_score.tradeoffs:
            action_items.append(f"Manage tradeoff: {tradeoff}")

        # Missing important context (non-blocking but noted)
        if context_result.missing_important:
            for f in context_result.missing_important:
                action_items.append(f"Clarify context: {f.replace('_', ' ').title()}")

        # ---- Overall verdict ----
        if critical_count > 0 or domain_score.verdict == "BLOCK" or red_kpi_warnings:
            overall_verdict = "BLOCK"
            risk_level = "CRITICAL" if critical_count > 0 else "HIGH"
        elif (
            high_count >= 2
            or (high_count >= 1 and amber_kpi_warnings)
            or context_result.verdict == "CONDITIONAL"
            or domain_score.verdict == "CONDITIONAL"
        ):
            overall_verdict = "CONDITIONAL"
            risk_level = "HIGH" if high_count >= 2 else "MEDIUM"
        elif high_count == 1 or amber_kpi_warnings:
            overall_verdict = "CONDITIONAL"
            risk_level = "MEDIUM"
        else:
            overall_verdict = "PASS"
            risk_level = "LOW"

        reasoning = (
            " | ".join(reasons)
            if reasons
            else (
                "No critical failure patterns detected. Recommendation passes domain knowledge check."
                if overall_verdict == "PASS"
                else "Medium-level risks identified. Proceed with mitigation plan."
            )
        )

        return overall_verdict, risk_level, reasoning, list(dict.fromkeys(action_items))  # dedup

    # ---------------------------------------------------------------- #
    # Public interface
    # ---------------------------------------------------------------- #

    def evaluate(
        self,
        recommendation: str,
        context: Optional[Dict[str, Any]] = None,
        top_k_rag: int = 4,
    ) -> DomainAuditResult:
        """
        Run all 7 domain knowledge patterns on a recommendation.

        Args:
            recommendation: Free-text supply chain recommendation.
            context: Dict with keys: industry, demand_pattern, supply_chain_maturity,
                     disruption_environment, planning_horizon, data_availability, scor_domain.
            top_k_rag: Number of RAG knowledge chunks to retrieve.

        Returns:
            DomainAuditResult with overall verdict and pattern-level details.
        """
        context = context or {}

        # Update industry from context if provided
        if context.get("industry"):
            self.kpi_validator = KPIValidator(industry=context["industry"])

        # ---- Pattern #1: SCOR classification ----
        scor_domain, scor_risks = self._classify_scor(context)

        # ---- Pattern #2: Challenger agent ----
        challenges = self.challenger.challenge(recommendation, context)
        challenger_summary = self.challenger.summarise(challenges)

        # ---- Pattern #3: KPI validation ----
        kpi_warnings = self.kpi_validator.validate(recommendation)

        # ---- Pattern #4: RAG store retrieval ----
        rag_query = f"{recommendation} {scor_domain} {context.get('industry', '')}".strip()
        rag_chunks = self.rag_store.query(rag_query, top_k=top_k_rag)

        # ---- Pattern #6: Domain scorer ----
        domain_score = self.domain_scorer.score(recommendation, context)

        # ---- Pattern #7: Context checker ----
        context_result = self.context_checker.check(context, recommendation)

        # ---- Synthesise final verdict ----
        overall_verdict, risk_level, reasoning, action_items = self._synthesise_verdict(
            context_result=context_result,
            challenger_summary=challenger_summary,
            kpi_warnings=kpi_warnings,
            domain_score=domain_score,
        )

        return DomainAuditResult(
            scor_domain=scor_domain,
            scor_risks=scor_risks,
            challenges=challenges,
            challenger_summary=challenger_summary,
            kpi_warnings=kpi_warnings,
            rag_chunks=rag_chunks,
            domain_score=domain_score,
            context_check=context_result,
            overall_verdict=overall_verdict,
            risk_level=risk_level,
            reasoning=reasoning,
            action_items=action_items,
        )

    def update_industry(self, industry: str) -> None:
        """Update the industry for KPI benchmarking mid-session."""
        self.industry = industry
        self.kpi_validator = KPIValidator(industry=industry)
