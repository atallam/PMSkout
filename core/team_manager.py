"""
Skout — Team Manager  v0.1
Handles all team-layer intelligence: adjacency detection, director-level
portfolio stats, and flag-for-collaboration actions.

Data store: data/team_ideas.json  (written by core/integrations.py)

Adjacency rules (in priority order):
  Strong  — same domain + same problem_id
  Moderate — same domain + same stakeholder_id
  Weak    — same domain only  (not surfaced — too noisy)

No external dependencies beyond stdlib.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


TEAM_IDEAS_PATH = Path(__file__).parent.parent / "data" / "team_ideas.json"

# Adjacency strength labels
STRONG   = "strong"    # same domain + same problem_id
MODERATE = "moderate"  # same domain + same stakeholder_id (different problem)


# ------------------------------------------------------------------ #
# Data classes
# ------------------------------------------------------------------ #

@dataclass
class AdjacencyAlert:
    """
    Represents a detected adjacency between the current idea and a team idea.

    Attributes:
        peer_title:    Title of the adjacent idea in the team pool.
        peer_author:   PM who submitted the adjacent idea.
        peer_domain:   Domain of the adjacent idea.
        peer_score:    Score of the adjacent idea (0–100).
        strength:      "strong" or "moderate" — drives urgency of display.
        reason:        Human-readable explanation (e.g. "Same problem: invoice matching").
        flagged:       True if a Team Lead has already flagged this pair for collaboration.
    """
    peer_title:  str
    peer_author: str
    peer_domain: str
    peer_score:  float
    strength:    str
    reason:      str
    flagged:     bool = False


@dataclass
class DirectorStats:
    """
    Portfolio-level stats for the Director read-only sidebar view.

    Attributes:
        total_ideas:        Total ideas in the team pool.
        domain_counts:      {domain: count} — how many ideas per domain.
        band_counts:        {band_label: count} — score band distribution.
        top_ideas:          Up to 5 highest-scoring ideas [{title, author, domain, score}].
        cross_domain_signals: Problem IDs appearing in 2+ different domains.
        most_active_pm:     Name of PM with most shared ideas (or "" if tied/empty).
    """
    total_ideas:          int
    domain_counts:        Dict[str, int]
    band_counts:          Dict[str, int]
    top_ideas:            List[Dict[str, Any]]
    cross_domain_signals: List[Dict[str, Any]]  # [{problem_id, domains, count}]
    most_active_pm:       str


# ------------------------------------------------------------------ #
# TeamManager
# ------------------------------------------------------------------ #

class TeamManager:
    """
    Interface for all team-layer operations.

    Usage:
        tm = TeamManager(team_id="default")
        alerts = tm.detect_adjacencies(domain="procurement", problem_id="invoice_reconciliation",
                                        stakeholder_id="finance", exclude_author="Avinash")
        stats  = tm.get_director_stats()
        tm.flag_for_collaboration("Idea A", "Idea B", flagged_by="Avinash", note="Worth a chat")
    """

    def __init__(
        self,
        team_id: str = "default",
        path: Optional[Path] = None,
    ):
        self.team_id = team_id
        self._path   = path or TEAM_IDEAS_PATH

    # ------------------------------------------------------------------ #
    # Pool access
    # ------------------------------------------------------------------ #

    def get_pool(self) -> List[Dict]:
        """Return all shared ideas for this team_id, most recent first."""
        if not self._path.exists():
            return []
        try:
            with open(self._path, encoding="utf-8") as f:
                all_ideas = json.load(f)
            pool = [i for i in all_ideas if i.get("team_id", "default") == self.team_id]
            return sorted(pool, key=lambda x: x.get("shared_date", ""), reverse=True)
        except (json.JSONDecodeError, OSError):
            return []

    def _save_pool_raw(self, all_ideas: List[Dict]) -> None:
        """Persist the full all-teams list back to disk."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(all_ideas, f, indent=2, ensure_ascii=False)

    def _load_all(self) -> List[Dict]:
        if not self._path.exists():
            return []
        try:
            with open(self._path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return []

    # ------------------------------------------------------------------ #
    # Adjacency detection
    # ------------------------------------------------------------------ #

    def detect_adjacencies(
        self,
        domain: str,
        problem_id: str,
        stakeholder_id: str,
        exclude_author: str = "",
    ) -> List[AdjacencyAlert]:
        """
        Find team ideas adjacent to the current evaluation.

        Returns alerts sorted by strength (strong first) then score descending.
        Ideas by the same author are excluded (a PM doesn't need alerts about
        their own previous ideas — that's handled by the personal history panel).

        Args:
            domain:         Q1 answer of the current idea being evaluated.
            problem_id:     Q2 answer (e.g. "invoice_reconciliation").
            stakeholder_id: Q3 answer (e.g. "finance").
            exclude_author: Name of the current PM — skips their own ideas.
        Returns:
            List of AdjacencyAlert, at most 3 shown (pruned to keep sidebar tight).
        """
        pool    = self.get_pool()
        alerts  = []

        for idea in pool:
            if idea.get("author", "") == exclude_author:
                continue  # skip own ideas
            if idea.get("domain", "") != domain:
                continue  # different domain — no adjacency

            peer_problem     = idea.get("problem_id", "")
            peer_stakeholder = idea.get("stakeholder_id", "")

            if peer_problem and peer_problem == problem_id:
                # Strong: same domain + same problem
                strength = STRONG
                reason   = f"Same problem focus: {_fmt(problem_id)}"
            elif peer_stakeholder and peer_stakeholder == stakeholder_id:
                # Moderate: same domain + same stakeholder, different problem
                strength = MODERATE
                reason   = f"Same stakeholder group in {_fmt(domain)}"
            else:
                continue  # weak / no signal — don't surface

            alerts.append(AdjacencyAlert(
                peer_title  = idea.get("title", "Untitled"),
                peer_author = idea.get("author", "A colleague"),
                peer_domain = idea.get("domain", domain),
                peer_score  = float(idea.get("score", 0)),
                strength    = strength,
                reason      = reason,
                flagged     = bool(idea.get("collaboration_flag", False)),
            ))

        # Sort: strong first, then by score descending; cap at 3 alerts
        alerts.sort(key=lambda a: (0 if a.strength == STRONG else 1, -a.peer_score))
        return alerts[:3]

    # ------------------------------------------------------------------ #
    # Flag for collaboration (Team Lead action)
    # ------------------------------------------------------------------ #

    def flag_for_collaboration(
        self,
        title_a: str,
        title_b: str,
        flagged_by: str,
        note: str = "",
    ) -> bool:
        """
        Mark two ideas as flagged for collaboration by a Team Lead.
        Both ideas are updated with collaboration_flag=True and references to each other.

        Args:
            title_a:    Title of first idea (must exist in pool).
            title_b:    Title of second idea (must exist in pool).
            flagged_by: Name of the Team Lead triggering the flag.
            note:       Optional short note explaining why they should collaborate.
        Returns:
            True if both ideas were found and updated; False otherwise.
        """
        all_ideas = self._load_all()
        pool_titles = {
            i.get("title", "").strip().lower(): i
            for i in all_ideas
            if i.get("team_id", "default") == self.team_id
        }

        idea_a = pool_titles.get(title_a.strip().lower())
        idea_b = pool_titles.get(title_b.strip().lower())
        if not idea_a or not idea_b:
            return False  # one or both titles not found

        flag_date = date.today().isoformat()
        for idea, peer_title in ((idea_a, title_b), (idea_b, title_a)):
            idea["collaboration_flag"]  = True
            idea["flagged_by"]          = flagged_by
            idea["flagged_with"]        = peer_title
            idea["flag_note"]           = note[:200]
            idea["flag_date"]           = flag_date

        self._save_pool_raw(all_ideas)
        return True

    def get_flagged_pairs(self) -> List[Tuple[Dict, Dict]]:
        """
        Return all collaboration-flagged idea pairs in the team pool.
        Each tuple is (idea_a, idea_b) — both sides of the flag.
        Used by the Team Lead sidebar panel.
        """
        pool   = self.get_pool()
        flagged = [i for i in pool if i.get("collaboration_flag")]
        seen   = set()
        pairs  = []
        for idea in flagged:
            peer_title = idea.get("flagged_with", "")
            key = tuple(sorted([idea.get("title", ""), peer_title]))
            if key not in seen:
                seen.add(key)
                peer = next((i for i in pool if i.get("title") == peer_title), None)
                pairs.append((idea, peer))
        return pairs

    # ------------------------------------------------------------------ #
    # Director stats (read-only portfolio view)
    # ------------------------------------------------------------------ #

    def get_director_stats(self) -> DirectorStats:
        """
        Compute portfolio-level stats for the Director sidebar view.
        All computation is in-memory from the team pool — no external calls.
        """
        pool = self.get_pool()

        if not pool:
            return DirectorStats(
                total_ideas=0, domain_counts={}, band_counts={},
                top_ideas=[], cross_domain_signals=[], most_active_pm="",
            )

        # Domain coverage
        domain_counts = dict(Counter(i.get("domain", "unknown") for i in pool))

        # Score band distribution
        def _band(score: float) -> str:
            s = float(score)
            if s >= 80: return "🚀 High Priority"
            if s >= 60: return "🔍 Promising"
            if s >= 40: return "⚠️ Needs Clarity"
            return "❌ Not Ready"

        band_counts = dict(Counter(_band(i.get("score", 0)) for i in pool))

        # Top ideas (by score, up to 5)
        top_ideas = sorted(
            [
                {
                    "title":  i.get("title", "Untitled")[:32],
                    "author": i.get("author", ""),
                    "domain": i.get("domain", ""),
                    "score":  float(i.get("score", 0)),
                }
                for i in pool
            ],
            key=lambda x: -x["score"],
        )[:5]

        # Cross-domain signals: problem_ids appearing in 2+ distinct domains
        problem_domains: Dict[str, set] = defaultdict(set)
        for idea in pool:
            pid = idea.get("problem_id", "")
            dom = idea.get("domain", "")
            if pid and dom:
                problem_domains[pid].add(dom)

        cross_domain_signals = [
            {
                "problem_id": pid,
                "domains":    sorted(doms),
                "count":      len(doms),
            }
            for pid, doms in problem_domains.items()
            if len(doms) >= 2
        ]
        cross_domain_signals.sort(key=lambda x: -x["count"])

        # Most active PM
        author_counts = Counter(i.get("author", "") for i in pool if i.get("author"))
        most_active   = author_counts.most_common(1)[0][0] if author_counts else ""

        return DirectorStats(
            total_ideas          = len(pool),
            domain_counts        = domain_counts,
            band_counts          = band_counts,
            top_ideas            = top_ideas,
            cross_domain_signals = cross_domain_signals[:3],  # cap at 3 for sidebar
            most_active_pm       = most_active,
        )


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

def _fmt(key: str) -> str:
    """Convert snake_case key to Title Case display string."""
    return key.replace("_", " ").title()
