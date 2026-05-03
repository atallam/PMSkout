"""
Ideas Like This — Phase 4
Pattern-matching engine: surface similar past ideas for the current idea.
Similarity is computed across domain, score band, problem type, and keyword overlap.
No external dependencies — pure Python.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


# ------------------------------------------------------------------ #
# Data model
# ------------------------------------------------------------------ #

@dataclass
class SimilarIdea:
    title: str
    domain: str
    score: float
    band: str         # "high_priority" | "promising" | "needs_clarity" | "not_ready"
    band_label: str
    date: str
    outcome: Optional[str]
    similarity_score: float   # 0.0 – 1.0
    similarity_reason: str    # human-readable explanation
    deep_dive: bool = False


# Score-band mapping (mirrors scoring_engine.py)
_BAND_FROM_SCORE = [
    (80, "high_priority",  "🟢 High Priority"),
    (60, "promising",      "🟡 Promising"),
    (40, "needs_clarity",  "🟠 Needs Clarity"),
    (0,  "not_ready",      "🔴 Not Ready"),
]

_BAND_LABELS = {
    "high_priority": "High Priority",
    "promising":     "Promising",
    "needs_clarity": "Needs Clarity",
    "not_ready":     "Not Ready",
}


def _band_from_score(score: float) -> str:
    for threshold, band, _ in _BAND_FROM_SCORE:
        if score >= threshold:
            return band
    return "not_ready"


# ------------------------------------------------------------------ #
# Keyword extractor (lightweight, no deps)
# ------------------------------------------------------------------ #

_STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "are", "was", "be", "as", "it",
    "its", "this", "that", "we", "our", "my", "your", "their", "will",
    "can", "do", "does", "not", "no", "more", "than", "into", "up",
    "what", "how", "why", "when", "which", "who", "would", "could",
    "should", "have", "has", "had", "been", "any", "all", "each",
}


def _tokenize(text: str) -> List[str]:
    words = re.findall(r"[a-z]{3,}", text.lower())
    return [w for w in words if w not in _STOPWORDS]


def _jaccard(set_a: set, set_b: set) -> float:
    if not set_a or not set_b:
        return 0.0
    inter = len(set_a & set_b)
    union = len(set_a | set_b)
    return inter / union if union else 0.0


# ------------------------------------------------------------------ #
# Similarity engine
# ------------------------------------------------------------------ #

class IdeasLikeThis:
    """
    Finds past ideas similar to the current one.

    Similarity weights:
      - domain match:       35 points  (exact match)
      - band match:         20 points  (same score band)
      - problem match:      20 points  (same detected problem type, if stored)
      - keyword overlap:    25 points  (Jaccard on title + description tokens)
    """

    DOMAIN_WEIGHT   = 0.35
    BAND_WEIGHT     = 0.20
    PROBLEM_WEIGHT  = 0.20
    KEYWORD_WEIGHT  = 0.25

    def __init__(self, data_path: Optional[str] = None):
        if data_path is None:
            data_path = str(Path(__file__).parent.parent / "data" / "ideas.json")
        self.data_path = data_path

    def _load_history(self) -> List[Dict]:
        try:
            with open(self.data_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def find(
        self,
        current_domain: str,
        current_score: float,
        current_title: str,
        current_description: str = "",
        current_problem: str = "",
        top_n: int = 3,
        min_similarity: float = 0.05,
    ) -> List[SimilarIdea]:
        """
        Return up to `top_n` past ideas most similar to the current idea,
        sorted by similarity_score descending.
        """
        history = self._load_history()
        if not history:
            return []

        current_band    = _band_from_score(current_score)
        current_tokens  = set(_tokenize(current_title + " " + current_description))

        results: List[SimilarIdea] = []

        for idea in history:
            title  = idea.get("title", "") or ""
            # Skip trivially identical titles (current idea in history)
            if title.strip().lower() == current_title.strip().lower():
                continue

            score  = float(idea.get("score", 0))
            domain = idea.get("domain", "")
            band   = idea.get("band") or _band_from_score(score)
            date   = idea.get("date", "")
            outcome= idea.get("outcome")
            deep   = bool(idea.get("deep_dive", False))
            prob   = idea.get("problem", "") or ""

            # ── Domain similarity ──
            domain_sim = 1.0 if domain == current_domain else 0.0

            # ── Band similarity ──
            band_sim = 1.0 if band == current_band else 0.0

            # ── Problem similarity ──
            if current_problem and prob:
                problem_sim = 1.0 if prob == current_problem else 0.0
            else:
                problem_sim = 0.0

            # ── Keyword overlap ──
            past_tokens = set(_tokenize(title + " " + idea.get("description", "")))
            keyword_sim = _jaccard(current_tokens, past_tokens)

            # ── Weighted total ──
            total = (
                self.DOMAIN_WEIGHT   * domain_sim  +
                self.BAND_WEIGHT     * band_sim     +
                self.PROBLEM_WEIGHT  * problem_sim  +
                self.KEYWORD_WEIGHT  * keyword_sim
            )

            if total < min_similarity:
                continue

            # ── Human reason ──
            reasons = []
            if domain_sim:
                reasons.append(f"same domain ({domain})")
            if band_sim:
                reasons.append(f"same score band ({_BAND_LABELS.get(band, band)})")
            if problem_sim:
                reasons.append("same problem type")
            if keyword_sim > 0.1:
                reasons.append(f"similar keywords ({keyword_sim:.0%} overlap)")
            reason = "; ".join(reasons) if reasons else "general similarity"

            results.append(SimilarIdea(
                title=title,
                domain=domain,
                score=score,
                band=band,
                band_label=_BAND_LABELS.get(band, band),
                date=date,
                outcome=outcome,
                similarity_score=round(total, 3),
                similarity_reason=reason,
                deep_dive=deep,
            ))

        # Sort by similarity descending, cap at top_n
        results.sort(key=lambda x: x.similarity_score, reverse=True)
        return results[:top_n]

    def get_pattern_summary(
        self,
        domain: str,
        current_score: float,
    ) -> Optional[str]:
        """
        Return a one-sentence pattern insight for the given domain,
        e.g. 'Your last 3 planning ideas averaged 82 — this one scores 78.'
        """
        history = self._load_history()
        domain_ideas = [i for i in history if i.get("domain") == domain]
        if len(domain_ideas) < 2:
            return None

        scores = [float(i.get("score", 0)) for i in domain_ideas[-10:]]
        avg = sum(scores) / len(scores)
        delta = current_score - avg
        direction = "above" if delta >= 0 else "below"
        return (
            f"Your last {len(scores)} {domain} idea(s) averaged "
            f"**{avg:.0f}** — this one is **{abs(delta):.0f} pts {direction}** that average."
        )
