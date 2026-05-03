"""
Skout — Pattern #6: Domain Scorer (Multi-Dimensional Rubric)
=============================================================
Replaces binary pass/fail with a 5-dimension weighted scorecard that forces
explicit tradeoff analysis before any PASS verdict can be issued.

Dimensions:
  1. cost_impact         — Does this save / cost money?
  2. resilience_impact   — Does this make the supply chain more or less resilient?
  3. service_level_impact — Does this help or hurt customer service levels?
  4. implementation_complexity — How hard is this to implement?
  5. time_to_value       — How quickly will benefits be realised?

Scoring:
  - Dimensions 1-3: [-1.0, +1.0] (negative = bad, positive = good)
  - Dimensions 4-5: [0.0, +1.0] (0 = hardest/slowest, 1 = easiest/fastest)
  - PASS threshold: weighted score > 0.55 AND resilience_impact > -0.3
  - BLOCK condition: resilience_impact <= -0.5

Usage:
    scorer = DomainScorer(llm_provider=factory.get_provider())
    result = scorer.score(recommendation_text, context)
    print(result.overall_score, result.verdict)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any


# ------------------------------------------------------------------ #
# Config
# ------------------------------------------------------------------ #

DIMENSION_WEIGHTS = {
    "cost_impact":               0.20,
    "resilience_impact":         0.35,  # Highest weight — resilience is hardest to recover
    "service_level_impact":      0.25,
    "implementation_complexity": 0.10,
    "time_to_value":             0.10,
}

DIMENSION_LABELS = {
    "cost_impact":               "Cost Impact",
    "resilience_impact":         "Resilience Impact",
    "service_level_impact":      "Service Level Impact",
    "implementation_complexity": "Implementation Complexity",
    "time_to_value":             "Time to Value",
}

DIMENSION_DESCRIPTIONS = {
    "cost_impact":               "Net financial impact: savings vs. total cost of ownership",
    "resilience_impact":         "Supply chain resilience: ability to absorb and recover from disruptions",
    "service_level_impact":      "Customer-facing service: fill rate, OTIF, perfect order rate",
    "implementation_complexity": "Ease of implementation: IT, change management, supplier readiness",
    "time_to_value":             "Speed to realise benefits: weeks (fast) vs. years (slow)",
}

PASS_THRESHOLD = 0.55
RESILIENCE_MIN = -0.30    # Any score below this blocks the recommendation
RESILIENCE_BLOCK = -0.50  # Hard block


# ------------------------------------------------------------------ #
# Result dataclass
# ------------------------------------------------------------------ #

@dataclass
class DomainScoreResult:
    dimension_scores: Dict[str, float]   # {dimension_id: score}
    weighted_score: float                # Final 0-1 weighted score
    verdict: str                         # PASS / CONDITIONAL / BLOCK
    blocking_reason: Optional[str]       # Set if verdict == BLOCK
    tradeoffs: List[str]                 # Human-readable tradeoff notes
    confidence: str                      # HIGH / MEDIUM / LOW
    source: str                          # "llm" or "rule_based"

    @property
    def verdict_emoji(self) -> str:
        return {"PASS": "✅", "CONDITIONAL": "⚠️", "BLOCK": "🚫"}.get(self.verdict, "❓")

    @property
    def verdict_color(self) -> str:
        return {"PASS": "#16a34a", "CONDITIONAL": "#ca8a04", "BLOCK": "#dc2626"}.get(self.verdict, "#6b7280")

    @property
    def score_pct(self) -> int:
        return int(self.weighted_score * 100)

    def to_dict(self) -> Dict:
        return {
            "dimension_scores": {
                k: {"score": v, "label": DIMENSION_LABELS[k], "description": DIMENSION_DESCRIPTIONS[k]}
                for k, v in self.dimension_scores.items()
            },
            "weighted_score": round(self.weighted_score, 3),
            "score_pct": self.score_pct,
            "verdict": self.verdict,
            "verdict_emoji": self.verdict_emoji,
            "verdict_color": self.verdict_color,
            "blocking_reason": self.blocking_reason,
            "tradeoffs": self.tradeoffs,
            "confidence": self.confidence,
            "source": self.source,
        }


# ------------------------------------------------------------------ #
# Domain Scorer
# ------------------------------------------------------------------ #

class DomainScorer:
    """
    Multi-dimensional supply chain scorecard.
    Uses LLM to rate each dimension if available, falls back to keyword heuristics.
    """

    def __init__(self, llm_provider=None):
        self.llm = llm_provider

    # ---------------------------------------------------------------- #
    # LLM scoring
    # ---------------------------------------------------------------- #

    def _build_llm_prompt(self, recommendation: str, context: Dict) -> str:
        ctx_str = "\n".join(f"  {k}: {v}" for k, v in context.items() if v) if context else "  No additional context."

        return f"""You are a supply chain strategy expert scoring a recommendation across 5 dimensions.

RECOMMENDATION:
\"\"\"{recommendation}\"\"\"

CONTEXT:
{ctx_str}

Score each dimension on the specified scale. Be realistic and conservative — most recommendations have tradeoffs.

DIMENSION SCORING GUIDE:
1. cost_impact: -1.0 (major cost increase) to +1.0 (major cost saving). 0 = neutral.
2. resilience_impact: -1.0 (severely degrades resilience) to +1.0 (significantly improves resilience). 0 = neutral. A score below -0.3 BLOCKS the recommendation.
3. service_level_impact: -1.0 (significantly hurts customer service) to +1.0 (significantly improves). 0 = neutral.
4. implementation_complexity: 0.0 (extremely complex, multi-year) to 1.0 (simple, weeks).
5. time_to_value: 0.0 (benefits take 3+ years) to 1.0 (benefits in <3 months).

Also identify 2-3 key tradeoffs (e.g. "Saves cost but reduces resilience if key supplier fails").

Format EXACTLY as:
COST_IMPACT: [score between -1.0 and 1.0]
RESILIENCE_IMPACT: [score between -1.0 and 1.0]
SERVICE_LEVEL_IMPACT: [score between -1.0 and 1.0]
IMPLEMENTATION_COMPLEXITY: [score between 0.0 and 1.0]
TIME_TO_VALUE: [score between 0.0 and 1.0]
TRADEOFF_1: [specific tradeoff description]
TRADEOFF_2: [specific tradeoff description]
TRADEOFF_3: [optional third tradeoff]
CONFIDENCE: [HIGH/MEDIUM/LOW based on how much context you have]"""

    def _parse_llm_scores(self, response: str) -> Optional[Dict[str, Any]]:
        """Parse LLM dimension scores from structured response."""
        if not response or response == "__RULE_BASED__":
            return None

        result: Dict[str, Any] = {"tradeoffs": [], "confidence": "MEDIUM"}
        field_map = {
            "COST_IMPACT": "cost_impact",
            "RESILIENCE_IMPACT": "resilience_impact",
            "SERVICE_LEVEL_IMPACT": "service_level_impact",
            "IMPLEMENTATION_COMPLEXITY": "implementation_complexity",
            "TIME_TO_VALUE": "time_to_value",
        }

        for label, key in field_map.items():
            m = re.search(rf"^{label}:\s*([-\d.]+)", response, re.MULTILINE | re.IGNORECASE)
            if m:
                try:
                    val = float(m.group(1))
                    # Clamp to valid range
                    if key in ("cost_impact", "resilience_impact", "service_level_impact"):
                        val = max(-1.0, min(1.0, val))
                    else:
                        val = max(0.0, min(1.0, val))
                    result[key] = val
                except ValueError:
                    pass

        # Extract tradeoffs
        for i in range(1, 4):
            m = re.search(rf"^TRADEOFF_{i}:\s*(.+)$", response, re.MULTILINE | re.IGNORECASE)
            if m:
                result["tradeoffs"].append(m.group(1).strip())

        # Confidence
        m = re.search(r"^CONFIDENCE:\s*(\w+)$", response, re.MULTILINE | re.IGNORECASE)
        if m:
            conf = m.group(1).upper()
            result["confidence"] = conf if conf in ("HIGH", "MEDIUM", "LOW") else "MEDIUM"

        # Only return if we got all 5 dimension scores
        required = list(field_map.values())
        if all(k in result for k in required):
            return result

        return None

    # ---------------------------------------------------------------- #
    # Rule-based fallback scoring
    # ---------------------------------------------------------------- #

    def _rule_based_score(self, recommendation: str) -> Dict[str, Any]:
        """Heuristic scoring based on keyword patterns."""
        text = recommendation.lower()

        # Cost impact heuristics
        cost_signals = {
            1.0: ["significant cost saving", "major cost reduction", "dramatically reduce cost"],
            0.5: ["cost saving", "cost reduction", "save money", "reduce spend", "cut cost"],
            0.0: ["cost neutral", "no additional cost"],
            -0.5: ["additional investment", "upfront cost", "capex required", "additional spend"],
            -1.0: ["significant investment", "major capex", "substantial cost increase"],
        }
        cost = self._heuristic_score(text, cost_signals)

        # Resilience impact heuristics
        resilience_signals = {
            1.0: ["improve resilience", "diversify suppliers", "dual source", "reduce risk"],
            0.5: ["backup supplier", "alternative source", "risk mitigation"],
            0.0: ["resilience neutral"],
            -0.3: ["single supplier", "sole source", "reduce safety stock", "cut inventory", "just-in-time"],
            -0.7: ["eliminate all safety stock", "single source critical", "offshore all production"],
        }
        resilience = self._heuristic_score(text, resilience_signals)

        # Service level impact heuristics
        service_signals = {
            1.0: ["improve service level", "increase fill rate", "better customer service"],
            0.5: ["improve delivery", "faster delivery", "reduce stockouts"],
            0.0: ["service neutral", "maintain service"],
            -0.3: ["slower delivery", "longer lead time"],
            -0.7: ["reduce service level", "accept more stockouts"],
        }
        service = self._heuristic_score(text, service_signals)

        # Implementation complexity (0=hard, 1=easy) heuristics
        complexity_signals = {
            0.9: ["quick win", "simple change", "no it required", "manual process"],
            0.6: ["moderate complexity", "existing system", "configuration change"],
            0.3: ["erp integration", "new system", "process redesign", "multi-phase"],
            0.1: ["complex transformation", "multi-year", "significant change management"],
        }
        complexity = self._heuristic_score(text, complexity_signals, default=0.5)

        # Time to value (0=slow, 1=fast) heuristics
        ttv_signals = {
            0.9: ["immediate", "within weeks", "quick win", "days"],
            0.6: ["within months", "3-6 months", "short term"],
            0.3: ["6-12 months", "medium term", "next year"],
            0.1: ["multi-year", "long term", "2+ years", "3 years"],
        }
        ttv = self._heuristic_score(text, ttv_signals, default=0.4)

        tradeoffs = []
        if cost > 0.3 and resilience < -0.2:
            tradeoffs.append("Cost saving may come at the expense of supply chain resilience")
        if service > 0.3 and cost < -0.2:
            tradeoffs.append("Service level improvement requires additional investment")
        if resilience > 0.3 and cost < 0:
            tradeoffs.append("Resilience improvement requires upfront cost — evaluate ROI timeline")

        return {
            "cost_impact": cost,
            "resilience_impact": resilience,
            "service_level_impact": service,
            "implementation_complexity": complexity,
            "time_to_value": ttv,
            "tradeoffs": tradeoffs,
            "confidence": "LOW",  # Rule-based is always LOW confidence
        }

    @staticmethod
    def _heuristic_score(text: str, signals: Dict[float, List[str]], default: float = 0.0) -> float:
        """Score text based on keyword signal mapping. Returns value closest to a match."""
        for score in sorted(signals.keys(), key=abs, reverse=True):
            for phrase in signals[score]:
                if phrase.lower() in text:
                    return score
        return default

    # ---------------------------------------------------------------- #
    # Verdict computation
    # ---------------------------------------------------------------- #

    @staticmethod
    def _compute_verdict(scores: Dict[str, float], weighted_score: float) -> tuple:
        """Compute verdict and blocking reason."""
        resilience = scores.get("resilience_impact", 0.0)

        if resilience <= RESILIENCE_BLOCK:
            return "BLOCK", f"Resilience impact is severely negative ({resilience:.2f}). This recommendation would significantly degrade supply chain resilience."

        if resilience < RESILIENCE_MIN:
            return "BLOCK", f"Resilience impact ({resilience:.2f}) falls below the minimum acceptable threshold of {RESILIENCE_MIN}. Redesign to protect resilience or add explicit mitigation."

        if weighted_score >= PASS_THRESHOLD:
            return "PASS", None
        elif weighted_score >= 0.35:
            return "CONDITIONAL", None
        else:
            return "BLOCK", f"Weighted score ({weighted_score:.2f}) is too low to approve. Revisit cost, resilience, and service level impacts."

    # ---------------------------------------------------------------- #
    # Public interface
    # ---------------------------------------------------------------- #

    def score(
        self,
        recommendation: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> DomainScoreResult:
        """
        Score a recommendation across all 5 dimensions.

        Args:
            recommendation: Free-text recommendation description.
            context: Optional dict with domain, industry, etc.

        Returns:
            DomainScoreResult with scores, verdict, and tradeoffs.
        """
        context = context or {}
        scores_data: Optional[Dict] = None
        source = "rule_based"

        # Try LLM scoring first
        if self.llm:
            try:
                prompt = self._build_llm_prompt(recommendation, context)
                system = (
                    "You are a supply chain strategy expert specialised in scoring initiative recommendations. "
                    "Be conservative and realistic. Most recommendations involve tradeoffs. "
                    "Never give all-positive scores — identify the tradeoffs."
                )
                response = self.llm.generate(prompt, system=system, mode="standard")
                if response and response != "__RULE_BASED__":
                    scores_data = self._parse_llm_scores(response)
                    if scores_data:
                        source = "llm"
            except Exception:
                pass

        # Fall back to rule-based
        if not scores_data:
            scores_data = self._rule_based_score(recommendation)

        # Extract dimension scores
        dimension_scores = {
            dim: scores_data.get(dim, 0.0)
            for dim in DIMENSION_WEIGHTS
        }

        # Compute weighted score (map all dimensions to [0,1] for weighting)
        weighted = 0.0
        for dim, weight in DIMENSION_WEIGHTS.items():
            raw = dimension_scores[dim]
            # Dimensions 1-3 are -1 to +1, normalise to 0-1
            if dim in ("cost_impact", "resilience_impact", "service_level_impact"):
                normalised = (raw + 1.0) / 2.0
            else:
                normalised = raw
            weighted += normalised * weight

        verdict, blocking_reason = self._compute_verdict(dimension_scores, weighted)

        return DomainScoreResult(
            dimension_scores=dimension_scores,
            weighted_score=round(weighted, 3),
            verdict=verdict,
            blocking_reason=blocking_reason,
            tradeoffs=scores_data.get("tradeoffs", []),
            confidence=scores_data.get("confidence", "LOW"),
            source=source,
        )
