"""
Skout — Pattern #2: Challenger Agent (Devil's Advocate)
========================================================
A dedicated agent whose sole job is to surface failure modes in supply chain
recommendations. It never approves — it only challenges.

Two modes:
  - Rule-based: keyword matching against failure_patterns.json (fast, no API cost)
  - LLM-enhanced: uses the active LLM to generate additional challenges (richer)

Usage:
    agent = ChallengerAgent(llm_provider=factory.get_provider())
    challenges = agent.challenge(recommendation_text, context)
    for c in challenges:
        print(c["name"], c["severity"], c["questions"])
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Any


# ------------------------------------------------------------------ #
# Data classes
# ------------------------------------------------------------------ #

@dataclass
class Challenge:
    pattern_id: str
    name: str
    severity: str          # CRITICAL / HIGH / MEDIUM / LOW
    description: str
    matched_triggers: List[str]
    challenge_questions: List[str]
    safe_conditions: List[str]
    example_failure: str
    source: str = "rule_based"   # "rule_based" or "llm"

    @property
    def severity_emoji(self) -> str:
        return {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🟢"}.get(self.severity, "⚪")

    @property
    def severity_order(self) -> int:
        return {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}.get(self.severity, 4)

    def to_dict(self) -> Dict:
        return {
            "pattern_id": self.pattern_id,
            "name": self.name,
            "severity": self.severity,
            "severity_emoji": self.severity_emoji,
            "description": self.description,
            "matched_triggers": self.matched_triggers,
            "challenge_questions": self.challenge_questions,
            "safe_conditions": self.safe_conditions,
            "example_failure": self.example_failure,
            "source": self.source,
        }


# ------------------------------------------------------------------ #
# Challenger Agent
# ------------------------------------------------------------------ #

class ChallengerAgent:
    """
    Devil's advocate agent. Surfaces failure modes in supply chain recommendations.
    Always challenges — never approves. The judge agent decides the final verdict.
    """

    _PATTERNS_FILE = Path(__file__).parent.parent / "domain_knowledge" / "failure_patterns.json"

    def __init__(self, llm_provider=None, use_llm: bool = True):
        """
        Args:
            llm_provider: Optional BaseLLMProvider. If None, rule-based only.
            use_llm: Whether to augment rule-based challenges with LLM analysis.
        """
        self.llm = llm_provider
        self.use_llm = use_llm and llm_provider is not None
        self._patterns = self._load_patterns()

    def _load_patterns(self) -> List[Dict]:
        if not self._PATTERNS_FILE.exists():
            return []
        with open(self._PATTERNS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("failure_patterns", [])

    # ---------------------------------------------------------------- #
    # Rule-based matching
    # ---------------------------------------------------------------- #

    def _match_rule_based(self, text: str) -> List[Challenge]:
        """Match recommendation text against known failure patterns."""
        text_lower = text.lower()
        matched: List[Challenge] = []

        for pattern in self._patterns:
            triggers_found = [
                t for t in pattern.get("triggers", [])
                if re.search(r"\b" + re.escape(t.lower()) + r"\b", text_lower)
                or t.lower() in text_lower
            ]
            if triggers_found:
                matched.append(Challenge(
                    pattern_id=pattern["id"],
                    name=pattern["name"],
                    severity=pattern.get("severity", "MEDIUM"),
                    description=pattern["description"],
                    matched_triggers=triggers_found,
                    challenge_questions=pattern.get("challenge_questions", []),
                    safe_conditions=pattern.get("safe_conditions", []),
                    example_failure=pattern.get("example_failure", ""),
                    source="rule_based",
                ))

        # Sort: CRITICAL first, then HIGH, MEDIUM, LOW
        matched.sort(key=lambda c: c.severity_order)
        return matched

    # ---------------------------------------------------------------- #
    # LLM-enhanced challenges
    # ---------------------------------------------------------------- #

    def _build_llm_prompt(self, recommendation: str, context: Dict, rule_challenges: List[Challenge]) -> str:
        existing = "\n".join(f"- {c.name}" for c in rule_challenges) if rule_challenges else "None detected yet."
        ctx_str = "\n".join(f"  {k}: {v}" for k, v in context.items() if v) if context else "  No additional context."

        return f"""You are a senior supply chain risk analyst. Your ONLY job is to find flaws, risks, and failure modes in supply chain project recommendations. You never approve — you challenge.

RECOMMENDATION TO STRESS-TEST:
\"\"\"{recommendation}\"\"\"

CONTEXT:
{ctx_str}

ALREADY IDENTIFIED RISKS (do NOT repeat these):
{existing}

Your task:
1. Identify 2-3 ADDITIONAL supply chain risks NOT already listed above.
2. For each risk, provide:
   - Risk name (short, specific)
   - Severity: CRITICAL / HIGH / MEDIUM / LOW
   - One-sentence description of why this is risky in supply chain context
   - One sharp challenge question the team must answer before proceeding

Focus on: data availability gaps, organisational readiness, supplier capability assumptions, hidden cost shifts, implementation complexity underestimation, and change management gaps.

Format your response EXACTLY as:
RISK: [name]
SEVERITY: [level]
DESCRIPTION: [one sentence]
QUESTION: [one question]
---
RISK: [name]
...

If no additional risks exist beyond those already identified, respond with: NO_ADDITIONAL_RISKS"""

    def _parse_llm_challenges(self, llm_response: str) -> List[Challenge]:
        """Parse structured LLM response into Challenge objects."""
        challenges: List[Challenge] = []

        if "NO_ADDITIONAL_RISKS" in llm_response:
            return challenges

        blocks = llm_response.split("---")
        for block in blocks:
            block = block.strip()
            if not block:
                continue

            name = self._extract_field(block, "RISK")
            severity = self._extract_field(block, "SEVERITY").upper()
            description = self._extract_field(block, "DESCRIPTION")
            question = self._extract_field(block, "QUESTION")

            if not name or not question:
                continue

            # Normalise severity
            if severity not in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
                severity = "MEDIUM"

            challenges.append(Challenge(
                pattern_id=f"llm_{name.lower().replace(' ', '_')[:30]}",
                name=name,
                severity=severity,
                description=description,
                matched_triggers=[],
                challenge_questions=[question],
                safe_conditions=[],
                example_failure="",
                source="llm",
            ))

        return challenges

    @staticmethod
    def _extract_field(text: str, field: str) -> str:
        match = re.search(rf"^{field}:\s*(.+)$", text, re.MULTILINE | re.IGNORECASE)
        return match.group(1).strip() if match else ""

    # ---------------------------------------------------------------- #
    # Public interface
    # ---------------------------------------------------------------- #

    def challenge(
        self,
        recommendation: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> List[Challenge]:
        """
        Run full challenger analysis on a recommendation.

        Args:
            recommendation: Free-text description of the supply chain recommendation.
            context: Optional dict with keys like 'domain', 'industry', 'company_size'.

        Returns:
            Sorted list of Challenge objects (CRITICAL first).
        """
        if not recommendation or not recommendation.strip():
            return []

        context = context or {}

        # Phase 1: Rule-based matching (always runs)
        rule_challenges = self._match_rule_based(recommendation)

        # Phase 2: LLM augmentation (if available)
        llm_challenges: List[Challenge] = []
        if self.use_llm and self.llm:
            try:
                prompt = self._build_llm_prompt(recommendation, context, rule_challenges)
                system = (
                    "You are a senior supply chain risk analyst specialising in finding project failure modes. "
                    "Be specific, practical, and supply-chain-literate. Never be encouraging — only challenge."
                )
                response = self.llm.generate(prompt, system=system, mode="standard")
                if response and response != "__RULE_BASED__":
                    llm_challenges = self._parse_llm_challenges(response)
            except Exception:
                # LLM failure is non-fatal — rule-based results still returned
                pass

        all_challenges = rule_challenges + llm_challenges
        all_challenges.sort(key=lambda c: c.severity_order)
        return all_challenges

    def summarise(self, challenges: List[Challenge]) -> Dict[str, Any]:
        """Return a summary dict for display."""
        if not challenges:
            return {
                "total": 0,
                "critical": 0,
                "high": 0,
                "medium": 0,
                "low": 0,
                "top_risk": None,
                "verdict": "NO_CHALLENGES_DETECTED",
                "verdict_label": "No failure patterns detected",
            }

        counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
        for c in challenges:
            counts[c.severity] = counts.get(c.severity, 0) + 1

        if counts["CRITICAL"] > 0:
            verdict = "BLOCK"
            verdict_label = "Critical risks — must resolve before proceeding"
        elif counts["HIGH"] >= 2:
            verdict = "CONDITIONAL"
            verdict_label = "Multiple high risks — conditional approval only"
        elif counts["HIGH"] >= 1:
            verdict = "CONDITIONAL"
            verdict_label = "High risk detected — requires mitigation plan"
        else:
            verdict = "PROCEED_WITH_CAUTION"
            verdict_label = "Medium/low risks only — proceed with awareness"

        return {
            "total": len(challenges),
            "critical": counts["CRITICAL"],
            "high": counts["HIGH"],
            "medium": counts["MEDIUM"],
            "low": counts["LOW"],
            "top_risk": challenges[0].to_dict() if challenges else None,
            "verdict": verdict,
            "verdict_label": verdict_label,
        }
