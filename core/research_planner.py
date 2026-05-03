"""
Skout — Research Plan Generator  v0.3
Produces domain-aware, adaptive research plans from scored answers.

Modes:
  quick_scan    — rule-based only (no LLM, ~instant)
  standard      — LLM-enriched with Haiku (~15 s)
  deep_research — LLM-enriched with Sonnet + extended thinking (~60 s)

Data source:
  All static lookup tables (interview questions, data signals, success criteria,
  research methods, hypotheses templates, riskiest assumptions) live in
  data/research_content.json.  Edit content there — no Python changes needed.

Label maps:
  Imported from core.constants so they stay in sync with app.py.
"""
from __future__ import annotations
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))

from core.constants import Q2_LABELS, Q3_LABELS, Q4_LABELS, FREQ_LABELS, SEV_LABELS, WK_LABELS, DOMAIN_LABELS
from core.scoring_engine import VerdictResult  # noqa
from llm.base import BaseLLMProvider           # noqa


# ------------------------------------------------------------------ #
# Load static content from JSON at module level (cached on import)
# ------------------------------------------------------------------ #

def _load_content() -> Dict:
    """
    Load research_content.json from the data/ directory.
    Searches up from this file's location so the module works regardless of cwd.
    Raises FileNotFoundError with a clear message if the file is missing.
    """
    here = Path(__file__).parent.parent  # repo root
    path = here / "data" / "research_content.json"
    if not path.exists():
        raise FileNotFoundError(
            f"Missing data/research_content.json — expected at {path}\n"
            "Re-run the extraction script or restore the file from git."
        )
    with open(path, encoding="utf-8") as f:
        return json.load(f)

_RC = _load_content()  # single load; keys documented below

# Convenience aliases (keeps call sites readable)
PROBLEM_INTERVIEW_QUESTIONS: Dict[str, List[Dict]] = _RC["problem_interview_questions"]
DOMAIN_INTERVIEW_QUESTIONS:  Dict[str, List[Dict]] = _RC["domain_interview_questions"]
PROBLEM_DATA_SIGNALS:        Dict[str, List[Dict]] = _RC["problem_data_signals"]
DOMAIN_DATA_SIGNALS:         Dict[str, List[Dict]] = _RC["domain_data_signals"]
PROBLEM_SUCCESS_CRITERIA:    Dict[str, List[Dict]] = _RC["problem_success_criteria"]
DEFAULT_SUCCESS_CRITERIA:    List[Dict]             = _RC["default_success_criteria"]
DOMAIN_HYPOTHESES:           Dict[str, str]         = _RC["domain_hypotheses"]
STAKEHOLDER_ACCESS:          Dict[str, Dict]        = _RC["stakeholder_access"]
SECONDARY_PARTICIPANTS:      Dict[str, List[Dict]]  = _RC["secondary_participants"]
RESEARCH_METHODS:            Dict[str, List[Dict]]  = _RC["research_methods"]
_RISKIEST:                   Dict[str, Dict]        = _RC["riskiest_assumptions"]


# ------------------------------------------------------------------ #
# LLM Prompts  (kept in Python — they contain logic-critical formatting)
# ------------------------------------------------------------------ #

SYSTEM_PROMPT = """You are Scout, a senior supply chain product management expert and research strategist.
You specialise in enterprise supply chain software across:
  - Planning & Forecasting (S&OP, demand, inventory, capacity)
  - Procurement & Sourcing (supplier risk, invoice reconciliation, contract compliance, spend management)
  - Repair & MRO (field service, parts management, warranty, depot operations)
  - Trade & Compliance (customs, duties, import/export regulatory)
  - Fraud & Risk (invoice fraud, warranty abuse, supplier collusion)

Your role is to generate rigorous, specific, and deeply actionable research plans for product managers
validating supply chain ideas. Generic plans are worse than useless — every output must be specific
to the domain, problem type, and stakeholder combination provided.

Research plan quality standards:
  - Interview questions must follow the Mom Test: ask about past behaviour, not hypothetical futures
  - Data signals must name the exact system source and what to look for, not just "check the ERP"
  - Success criteria must be binary and observable — not "learn more about the problem"
  - Assumptions must be specific to this idea, not generic boilerplate
  - Riskiest assumption should be the one that, if wrong, makes the entire idea worthless

Always return valid JSON matching the schema provided. Be specific, be supply-chain-aware."""

STANDARD_PROMPT = """
Generate a detailed, actionable research plan for this supply chain product idea.

IDEA:
  Title: {idea_title}
  Description: {idea_description}

EVALUATION CONTEXT:
  Domain: {domain}
  Problem: {problem}
  Primary Stakeholder: {stakeholder}
  Current State: {current_state}
  Impact — Frequency: {frequency} | Severity: {severity} | Workaround Cost: {workaround}
  Signal Source: {origin}
  Verdict Score: {score}/100{cost_estimate_line}

BASELINE PLAN (improve and enrich — do not copy verbatim):
  Hypothesis: {baseline_hypothesis}

Return ONLY valid JSON:
{{
  "hypothesis": "A specific, falsifiable 2–3 sentence hypothesis grounded in the problem and context above",
  "key_assumptions": [
    "The most critical assumption about the user — specific to this problem",
    "The most critical assumption about market gap or timing",
    "The most critical assumption about technical or organisational feasibility"
  ],
  "riskiest_assumption": "The single assumption that, if wrong, makes this idea not worth building",
  "cheapest_validation": "The fastest, lowest-cost way to test the riskiest assumption — be specific",
  "interview_questions": [
    {{"question": "Past-behaviour question specific to this problem (Mom Test)", "intent": "Process|Pain|Outcome|History|Risk", "intent_desc": "why this question matters for this specific idea"}},
    {{"question": "...", "intent": "...", "intent_desc": "..."}},
    {{"question": "...", "intent": "...", "intent_desc": "..."}},
    {{"question": "...", "intent": "...", "intent_desc": "..."}},
    {{"question": "...", "intent": "...", "intent_desc": "..."}}
  ],
  "participant_notes": "Specific guidance on recruiting participants for this domain and problem type",
  "data_signals": [
    {{"metric": "specific metric name", "source": "exact system or team", "description": "what to look for and why it validates or disproves the hypothesis"}}
  ],
  "success_criteria": [
    {{"criterion": "Specific, binary, observable outcome that would confirm this problem is real", "type": "Confirmed"}},
    {{"criterion": "A number that, if retrieved, would quantify the opportunity size", "type": "Quantified"}},
    {{"criterion": "A result that would explicitly disprove the core hypothesis", "type": "Disproved"}},
    {{"criterion": "A specific adoption blocker that must be understood before spec is written", "type": "Blocker"}}
  ],
  "timeline_guidance": "Recommended sprint duration and pacing for this specific research plan"
}}
"""

DEEP_RESEARCH_PROMPT = """
Perform a DEEP RESEARCH analysis for this supply chain product idea.
Use extended reasoning — generate competing hypotheses, stress-test assumptions,
identify second-order effects, and surface the most dangerous counter-arguments.

IDEA:
  Title: {idea_title}
  Description: {idea_description}

EVALUATION CONTEXT:
  Domain: {domain}
  Problem: {problem}
  Primary Stakeholder: {stakeholder}
  Current State: {current_state}
  Impact — Frequency: {frequency} | Severity: {severity} | Workaround Cost: {workaround}
  Signal Source: {origin}
  Verdict Score: {score}/100 (Deep Research unlocked — this idea passed the high-priority threshold){cost_estimate_line}

Return ONLY valid JSON:
{{
  "competing_hypotheses": [
    {{
      "hypothesis": "Primary hypothesis — the most likely interpretation of the signals",
      "confidence": "high|medium|low",
      "key_assumptions": ["assumption 1", "assumption 2"],
      "evidence_for": "What in the evaluation supports this interpretation",
      "evidence_against": "What challenges or contradicts this interpretation"
    }},
    {{
      "hypothesis": "Alternative hypothesis — different but plausible interpretation of the same signals",
      "confidence": "high|medium|low",
      "key_assumptions": ["assumption 1", "assumption 2"],
      "evidence_for": "...",
      "evidence_against": "..."
    }},
    {{
      "hypothesis": "Contrarian hypothesis — what if the real problem is fundamentally different from what was stated",
      "confidence": "high|medium|low",
      "key_assumptions": ["assumption 1", "assumption 2"],
      "evidence_for": "...",
      "evidence_against": "..."
    }}
  ],
  "counter_arguments": [
    "The strongest argument against this idea being worth building — be specific to the domain and problem",
    "Second counter-argument — different dimension (market, technical, organisational, or timing)",
    "Third counter-argument"
  ],
  "second_order_effects": [
    "What this solution might enable beyond the stated problem — adjacent opportunity",
    "What risk or new dependency this solution might create",
    "Adjacent problem this solution might expose or amplify"
  ],
  "interview_questions": [
    {{"question": "Past-behaviour question specific to this problem (Mom Test quality)", "intent": "Process|Pain|Outcome|History|Risk", "intent_desc": "..."}}
  ],
  "participant_notes": "Specific guidance for this domain, problem type, and stakeholder combination",
  "data_signals": [
    {{"metric": "...", "source": "...", "description": "...", "signal_confidence": "high|medium|low"}}
  ],
  "success_criteria": [
    {{"criterion": "...", "type": "Confirmed|Quantified|Disproved|Blocker"}}
  ],
  "riskiest_assumption": "The single assumption that, if wrong, kills the idea entirely — specific to this idea",
  "cheapest_validation": "The fastest, lowest-cost experiment to test the riskiest assumption",
  "timeline_guidance": "Recommended research sprint duration and pacing"
}}
"""


# ------------------------------------------------------------------ #
# Research Plan Generator
# ------------------------------------------------------------------ #

class ResearchPlanner:
    """
    Generates domain-aware, problem-specific research plans from scored answers.

    The generator has three modes:
      quick_scan    — rule-based lookups only, no LLM call
      standard      — rule-based baseline enriched by Haiku LLM call
      deep_research — rule-based baseline enriched by Sonnet + extended thinking

    All static domain content (questions, signals, criteria) is loaded from
    data/research_content.json at module import time via the _RC dict.
    """

    def __init__(self, provider: Optional[Any] = None):
        self.provider = provider

    # ------------------------------------------------------------------ #
    # Public interface
    # ------------------------------------------------------------------ #

    def generate(
        self,
        answers: Dict[str, Any],
        verdict: Any,
        idea_title: str = "",
        idea_description: str = "",
        mode: str = "standard",
        cost_estimate: str = "",
    ) -> Dict[str, Any]:
        """
        Generate a research plan from scored answers.

        Args:
            answers:          QuestionEngine.answers dict (q1–q5 + origin)
            verdict:          VerdictResult from ScoringEngine
            idea_title:       PM-provided idea title
            idea_description: PM-provided idea description
            mode:             "quick_scan" | "standard" | "deep_research"
            cost_estimate:    Optional free-text cost/impact estimate
        Returns:
            Plan dict with hypothesis, interview_questions, data_signals, etc.
        """
        domain     = answers.get("q1", "")
        problem_id = answers.get("q2", "")
        q3         = answers.get("q3", "")
        q4         = answers.get("q4", "")
        q5         = answers.get("q5", {})
        problem_key = f"{domain}__{problem_id}"

        # ── Rule-based lookups (fallback chain: specific → domain → procurement) ──
        interview_questions = (
            PROBLEM_INTERVIEW_QUESTIONS.get(problem_key)
            or DOMAIN_INTERVIEW_QUESTIONS.get(domain)
            or DOMAIN_INTERVIEW_QUESTIONS.get("procurement", [])
        )
        data_signals = (
            PROBLEM_DATA_SIGNALS.get(problem_key)
            or DOMAIN_DATA_SIGNALS.get(domain)
            or DOMAIN_DATA_SIGNALS.get("procurement", [])
        )
        success_criteria = (
            PROBLEM_SUCCESS_CRITERIA.get(problem_key)
            or DEFAULT_SUCCESS_CRITERIA
        )

        riskiest, cheapest = self._infer_riskiest_assumption(domain, problem_id, q4, q5)
        participants       = self._build_participants(domain, q3)
        hypothesis         = self._build_hypothesis(domain, problem_id, q3, q4, q5, answers)
        research_methods   = RESEARCH_METHODS.get(domain, RESEARCH_METHODS.get("procurement", []))
        timeline_guidance  = self._get_timeline(mode, len(participants))

        plan: Dict[str, Any] = {
            "source":               "rule_based",
            "domain":               domain,
            "domain_label":         DOMAIN_LABELS.get(domain, domain.capitalize()),
            "problem_id":           problem_id,
            "problem_label":        Q2_LABELS.get(problem_id, problem_id),
            "idea_title":           idea_title,
            "_idea_description":    idea_description,  # underscore = internal, not displayed
            "_answers":             answers,            # underscore = internal
            "hypothesis":           hypothesis,
            "competing_hypotheses": [],
            "counter_arguments":    [],
            "second_order_effects": [],
            "interview_questions":  list(interview_questions or []),
            "participants":         participants,
            "participant_notes":    "",
            "data_signals":         list(data_signals or []),
            "success_criteria":     list(success_criteria or DEFAULT_SUCCESS_CRITERIA),
            "research_methods":     research_methods,
            "riskiest_assumption":  riskiest,
            "cheapest_validation":  cheapest,
            "cost_estimate":        cost_estimate,
            "timeline_guidance":    timeline_guidance,
            "score":                getattr(verdict, "final_score", 0),
            "band":                 getattr(verdict, "band", ""),
        }

        # ── Optional LLM enrichment ───────────────────────────────────────
        if (
            self.provider is not None
            and self.provider.is_available()
            and mode in ("standard", "deep_research")
        ):
            raw = self.provider.generate(
                prompt=self._build_prompt(plan, verdict, mode, cost_estimate),
                system=SYSTEM_PROMPT,
                mode=mode,
            )
            if raw and raw != "__RULE_BASED__":
                plan = self._merge_llm_output(raw, plan, mode)

        return plan

    # ------------------------------------------------------------------ #
    # Participant builder
    # ------------------------------------------------------------------ #

    def _build_participants(self, domain: str, q3: str) -> List[Dict]:
        """Build primary + secondary participant list from stakeholder access data."""
        participants: List[Dict] = []
        if q3:
            info = STAKEHOLDER_ACCESS.get(q3, {})
            participants.append({
                "role":   Q3_LABELS.get(q3, q3),
                "count":  "3–5",
                "access": info.get("access", "Medium"),
                "note":   info.get("note", ""),
                "known":  False,
            })
        for sec in SECONDARY_PARTICIPANTS.get(domain, []):
            participants.append({**sec, "known": False})
        return participants

    # ------------------------------------------------------------------ #
    # Hypothesis builder
    # ------------------------------------------------------------------ #

    def _build_hypothesis(
        self, domain: str, problem_id: str, q3: str, q4: str, q5: Dict, answers: Dict
    ) -> str:
        """
        Build a human-readable hypothesis from answers using domain templates
        stored in DOMAIN_HYPOTHESES (data/research_content.json).
        Falls back to a generic sentence on KeyError.
        """
        template = DOMAIN_HYPOTHESES.get(domain, DOMAIN_HYPOTHESES.get("procurement", ""))
        if not template:
            return ""
        stakeholder   = Q3_LABELS.get(q3, "supply chain stakeholders")
        problem       = Q2_LABELS.get(problem_id, "this problem")
        frequency     = FREQ_LABELS.get(q5.get("frequency", ""), "regularly")
        severity      = SEV_LABELS.get(q5.get("severity", ""), "creates friction")
        current_state = Q4_LABELS.get(q4, "existing processes")
        workaround    = WK_LABELS.get(q5.get("workaround_effort", ""), "manual workarounds")
        try:
            return template.format(
                stakeholder=stakeholder, problem=problem, frequency=frequency,
                severity=severity, current_state=current_state, workaround=workaround,
            )
        except KeyError:
            return f"{stakeholder} face {problem} — a clear opportunity for a targeted supply chain solution."

    # ------------------------------------------------------------------ #
    # Timeline guidance
    # ------------------------------------------------------------------ #

    def _get_timeline(self, mode: str, n_participants: int) -> str:
        """Return practical timeline guidance based on mode and participant count."""
        if mode == "deep_research":
            return (
                "Allow 3–4 weeks: 1 week for scheduling and desk research, "
                "2 weeks for interviews and data pulls, 1 week for synthesis. "
                "Aim for at least 5 completed interviews before drawing conclusions."
            )
        if n_participants >= 3:
            return (
                "Allow 2–3 weeks: schedule interviews in the first week, "
                "run data pulls in parallel, synthesise findings in week 3. "
                "Don't wait for all interviews to complete before pulling data."
            )
        return (
            "Allow 1–2 weeks for a focused validation sprint. "
            "Target 3–5 interviews minimum before updating your verdict."
        )

    # ------------------------------------------------------------------ #
    # LLM prompt builder
    # ------------------------------------------------------------------ #

    def _build_prompt(self, plan: Dict, verdict: Any, mode: str, cost_estimate: str) -> str:
        """Build the LLM prompt string from plan metadata and verdict."""
        answers = plan.get("_answers", {})
        q5      = answers.get("q5", {})
        cost_line = f"\nEstimated cost impact: {cost_estimate}" if cost_estimate else ""
        template  = DEEP_RESEARCH_PROMPT if mode == "deep_research" else STANDARD_PROMPT
        return template.format(
            idea_title          = plan.get("idea_title", ""),
            idea_description    = plan.get("_idea_description", ""),
            domain              = plan.get("domain_label", plan.get("domain", "")),
            problem             = plan.get("problem_label", plan.get("problem_id", "")),
            stakeholder         = Q3_LABELS.get(answers.get("q3", ""), answers.get("q3", "")),
            current_state       = Q4_LABELS.get(answers.get("q4", ""), answers.get("q4", "")),
            frequency           = FREQ_LABELS.get(q5.get("frequency", ""), q5.get("frequency", "")),
            severity            = SEV_LABELS.get(q5.get("severity", ""), q5.get("severity", "")),
            workaround          = WK_LABELS.get(q5.get("workaround_effort", ""), q5.get("workaround_effort", "")),
            origin              = answers.get("origin", ""),
            score               = int(getattr(verdict, "final_score", 0)),
            cost_estimate_line  = cost_line,
            baseline_hypothesis = plan.get("hypothesis", ""),
            riskiest_assumption = plan.get("riskiest_assumption", ""),
        )

    # ------------------------------------------------------------------ #
    # LLM output merging
    # ------------------------------------------------------------------ #

    def _merge_llm_output(self, raw: str, plan: Dict, mode: str) -> Dict:
        """
        Parse LLM JSON response and merge into the rule-based plan.
        LLM content takes precedence over rule-based where it's non-empty.
        Falls back to the original plan on any parse error — never crashes.
        """
        json_match = re.search(r"\{[\s\S]*\}", raw)
        if not json_match:
            return plan
        try:
            llm_data = json.loads(json_match.group())
        except json.JSONDecodeError:
            return plan

        merged = dict(plan)
        merged["source"] = "llm_deep" if mode == "deep_research" else "llm_standard"

        # Scalar fields — prefer LLM if non-empty
        for field in ("hypothesis", "riskiest_assumption", "cheapest_validation",
                      "timeline_guidance", "participant_notes"):
            val = llm_data.get(field, "").strip()
            if val:
                merged[field] = val

        # List fields — prefer LLM if non-empty list
        for field in ("interview_questions", "data_signals", "success_criteria",
                      "competing_hypotheses", "counter_arguments", "second_order_effects"):
            val = llm_data.get(field)
            if isinstance(val, list) and val:
                merged[field] = val

        return merged

    # ------------------------------------------------------------------ #
    # Riskiest assumption inference
    # ------------------------------------------------------------------ #

    def _infer_riskiest_assumption(
        self, domain: str, problem_id: str, q4: str, q5: Dict
    ) -> Tuple[str, str]:
        """
        Return (riskiest_assumption, cheapest_validation) from data/research_content.json.
        Special cases: not_handled answer and rare frequency take precedence over domain.
        """
        freq = q5.get("frequency", "")

        # Special-case overrides (checked before domain lookup)
        if q4 == "not_handled":
            r = _RISKIEST["_not_handled"]
        elif freq == "rare":
            r = _RISKIEST["_rare_frequency"]
        else:
            r = _RISKIEST.get(domain, _RISKIEST["_default"])

        return r["riskiest"], r["cheapest"]
