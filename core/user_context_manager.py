"""
Skout — User Context Manager
Handles all personalisation: profile setup, passive learning from usage,
context injection into question flow and research plans.

Phases:
  0 — Onboarding   (0 ideas submitted)
  1 — Learning     (1–5 ideas)  : detects domain patterns
  2 — Adapting     (6–15 ideas) : unlocks scoring weights, custom sources
  3 — Personalising (16+ ideas) : outcome tracking, pattern alerts
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))


# ------------------------------------------------------------------ #
# Phase thresholds
# ------------------------------------------------------------------ #

PHASE_THRESHOLDS = {0: 0, 1: 1, 2: 6, 3: 16}

ORG_TYPES = [
    "Telecom Operator", "OEM / Manufacturer", "3PL / Logistics Provider",
    "Retailer / E-commerce", "Healthcare / MedTech", "Energy / Utilities",
    "Aerospace & Defence", "Automotive", "Financial Services", "Other",
]
ORG_SIZES  = ["Startup (<50)", "SMB (50–500)", "Mid-market (500–5k)", "Enterprise (5k+)"]
REGIONS    = ["North America", "EMEA", "APAC", "LATAM", "Global"]
DATA_SYSTEMS = [
    "SAP S/4HANA", "SAP ECC", "Oracle Fusion", "Oracle EBS",
    "ServiceNow", "Salesforce", "Microsoft Dynamics", "JD Edwards",
    "Infor", "Blue Yonder / JDA", "Kinaxis", "Manhattan Associates",
    "Custom / In-house", "Other",
]
DOMAIN_LABELS = {
    "planning":    "Planning & Forecasting",
    "procurement": "Procurement & Sourcing",
    "repair":      "Repair & MRO",
    "trade":       "Trade & Compliance",
    "fraud":       "Fraud & Risk",
}
METHOD_LABELS = {
    "user_interviews": "User Interviews",
    "data_pull":       "Data Pull",
    "observation":     "Process Observation",
    "survey":          "Survey",
    "case_review":     "Case Review",
}


class UserContextManager:
    """
    Single interface for reading, writing, and applying user context.

    Usage:
        ucm = UserContextManager()
        ucm.load()
        if not ucm.is_onboarded():
            ... show onboarding ...
        ucm.record_idea_submitted("procurement", score=87.0)
        plan = ucm.inject_into_plan(plan)
    """

    def __init__(
        self,
        context_path: str = "config/user_context.yaml",
        ideas_path:   str = "data/ideas.json",
    ):
        """
        Set file paths and initialise empty in-memory state.
        Call load() immediately after construction before reading any values.

        Args:
            context_path: Path to user_context.yaml (profile, preferences, learning data).
            ideas_path:   Path to data/ideas.json (idea submission history).
        """
        self.context_path = Path(context_path)
        self.ideas_path   = Path(ideas_path)
        self._ctx: Dict   = {}
        self._ideas: List[Dict] = []

    # ------------------------------------------------------------------ #
    # Load / Save
    # ------------------------------------------------------------------ #

    def load(self) -> "UserContextManager":
        """
        Load user_context.yaml and ideas.json into memory.
        Creates data/ directory and an empty ideas.json if they do not yet exist.

        Returns:
            self — allows chaining: ``ucm = UserContextManager().load()``.
        """
        if self.context_path.exists():
            with open(self.context_path, encoding="utf-8") as f:
                self._ctx = yaml.safe_load(f) or {}
        else:
            self._ctx = {}

        self.ideas_path.parent.mkdir(parents=True, exist_ok=True)
        if self.ideas_path.exists():
            with open(self.ideas_path, encoding="utf-8") as f:
                self._ideas = json.load(f)
        else:
            self._ideas = []
            self._save_ideas()

        return self

    def save(self) -> None:
        """Persist user context YAML."""
        with open(self.context_path, "w", encoding="utf-8") as f:
            yaml.dump(self._ctx, f, default_flow_style=False, allow_unicode=True)

    def _save_ideas(self) -> None:
        """Persist the in-memory ideas list to data/ideas.json (pretty-printed JSON)."""
        with open(self.ideas_path, "w", encoding="utf-8") as f:
            json.dump(self._ideas, f, indent=2)

    # ------------------------------------------------------------------ #
    # Phase & onboarding
    # ------------------------------------------------------------------ #

    def is_onboarded(self) -> bool:
        """True if the user has completed onboarding (profile has a role or name set)."""
        profile = self._ctx.get("profile", {})
        return bool(profile.get("role") or profile.get("name"))

    def get_phase(self) -> int:
        """
        Return the user's current personalisation phase (0–3) based on how many
        ideas they have submitted against the PHASE_THRESHOLDS config.

        Returns:
            0 = Onboarding, 1 = Learning, 2 = Adapting, 3 = Personalising.
        """
        n = self._learning("ideas_submitted")
        if n >= PHASE_THRESHOLDS[3]:
            return 3
        if n >= PHASE_THRESHOLDS[2]:
            return 2
        if n >= PHASE_THRESHOLDS[1]:
            return 1
        return 0

    def phase_label(self) -> str:
        """Human-readable label for the current personalisation phase."""
        labels = {0: "Onboarding", 1: "Learning", 2: "Adapting", 3: "Personalising"}
        return labels[self.get_phase()]

    def ideas_to_next_phase(self) -> int:
        """
        Number of additional idea submissions needed to advance to the next phase.
        Returns 0 when already at Phase 3 (maximum personalisation).
        """
        phase = self.get_phase()
        if phase == 3:
            return 0
        next_threshold = PHASE_THRESHOLDS[phase + 1]
        current = self._learning("ideas_submitted")
        return max(0, next_threshold - current)

    # ------------------------------------------------------------------ #
    # Setup from onboarding form
    # ------------------------------------------------------------------ #

    def apply_onboarding(self, form: Dict) -> None:
        """
        Called once after the onboarding wizard is submitted.
        form keys: name, role, org_name, org_type, org_size, regions,
                   primary_domains, data_sources, interview_count, deep_think_threshold
        """
        self._ctx["profile"] = {
            "id":   self._ctx.get("profile", {}).get("id", ""),
            "name": form.get("name", ""),
            "role": form.get("role", ""),
            "organization": {
                "name":    form.get("org_name", ""),
                "type":    form.get("org_type", ""),
                "size":    form.get("org_size", ""),
                "regions": form.get("regions", []),
            },
        }
        self._ctx["domain_preferences"] = {
            "primary":      form.get("primary_domains", [""])[0] if form.get("primary_domains") else "",
            "secondary":    form.get("primary_domains", [])[1:],
            "wip_interest": [],
        }
        prefs = self._ctx.setdefault("research_preferences", {})
        prefs["default_interview_count"] = form.get("interview_count", 5)
        prefs["deep_think_threshold"]    = form.get("deep_think_threshold", 80)
        prefs["preferred_methods"]       = form.get("preferred_methods", [])
        prefs["custom_data_sources"]     = form.get("data_sources", [])
        prefs.setdefault("known_stakeholders", [])
        self.save()

    # ------------------------------------------------------------------ #
    # Learning — record events
    # ------------------------------------------------------------------ #

    def record_idea_submitted(
        self,
        domain: str,
        idea_title: str = "",
        score: float = 0.0,
        deep_dive: bool = False,
        answers: dict = None,
        verdict_dict: dict = None,
    ) -> None:
        """Call this every time a verdict is reached.

        Args:
            domain:       Q1 domain id (e.g. 'planning').
            idea_title:   Human-readable idea title / problem description.
            score:        Final verdict score (0-100).
            deep_dive:    Whether deep-dive was unlocked.
            answers:      Full QuestionEngine answers dict for replay.
            verdict_dict: Serialized VerdictResult (from VerdictResult.to_dict()).
        """
        # Update domain history
        dh = self._learning_dict("domain_history")
        dh[domain] = dh.get(domain, 0) + 1
        self._set_learning("domain_history", dh)

        # Increment counter
        self._set_learning("ideas_submitted", self._learning("ideas_submitted") + 1)

        # Auto-detect primary domain after 3 ideas
        top = self._top_domain()
        if top:
            self._ctx.setdefault("domain_preferences", {})["primary"] = top

        # Save idea to history (with full replay data)
        self._ideas.append({
            "title":       idea_title,
            "domain":      domain,
            "score":       score,
            "deep_dive":   deep_dive,
            "outcome":     None,
            "date":        str(date.today()),
            "answers":     answers or {},
            "verdict":     verdict_dict or {},
        })
        self._save_ideas()
        self.save()

    def record_research_completed(self, methods_used: List[str]) -> None:
        """
        Increment the research-completed counter and append newly-used methods
        to the user's preferred_methods list (avoids duplicates).

        Args:
            methods_used: List of method names (e.g. ["User Interviews", "Data Pull"]).
        """
        self._set_learning(
            "research_completed", self._learning("research_completed") + 1
        )
        # Learn preferred methods
        prefs = self._ctx.setdefault("research_preferences", {})
        existing = prefs.get("preferred_methods", [])
        for m in methods_used:
            if m not in existing:
                existing.append(m)
        prefs["preferred_methods"] = existing
        self.save()

    def record_outcome(self, idea_idx: int, outcome: str) -> None:
        """outcome: 'pursued' | 'abandoned' | 'validated' | 'deprioritised'"""
        if 0 <= idea_idx < len(self._ideas):
            self._ideas[idea_idx]["outcome"] = outcome
            self._save_ideas()
        self._set_learning(
            "outcomes_tracked", self._learning("outcomes_tracked") + 1
        )
        self.save()

    # ------------------------------------------------------------------ #
    # Personalisation — read context for injection
    # ------------------------------------------------------------------ #

    def get_suggested_domain(self) -> Optional[str]:
        """
        Return the domain to pre-select in Q1, if one is clearly dominant.
        Only kicks in at Phase 1+ and if one domain has ≥60% of submissions.
        """
        if self.get_phase() < 1:
            return None
        dh = self._learning_dict("domain_history")
        if not dh:
            return None
        total = sum(dh.values())
        top_domain, top_count = max(dh.items(), key=lambda x: x[1])
        if total >= 2 and (top_count / total) >= 0.6:
            return top_domain
        return None

    def get_custom_data_sources(self) -> List[str]:
        """Return list of data system names the user connected during onboarding."""
        return (
            self._ctx.get("research_preferences", {}).get("custom_data_sources", [])
            or []
        )

    def get_known_stakeholders(self) -> List[Dict]:
        """
        Return the user's pre-populated stakeholder roster.
        Each entry: {role, access_level, notes}.
        These are injected into research plans as 'Known contact' participants.
        """
        return (
            self._ctx.get("research_preferences", {}).get("known_stakeholders", [])
            or []
        )

    def get_deep_think_threshold(self) -> int:
        """
        Return the minimum score required to unlock the Research Plan (default 80).
        Configurable during onboarding and stored in user_context.yaml.
        """
        return int(
            self._ctx.get("research_preferences", {}).get(
                "deep_think_threshold", 80
            )
            or 80
        )

    def get_scoring_weights(self) -> Optional[Dict]:
        """
        Return custom dimension-weight overrides if enabled at Phase 2+, else None.
        Weights are stored under scoring_customization.weights in user_context.yaml.
        """
        custom = self._ctx.get("scoring_customization", {})
        if custom.get("enabled") and custom.get("weights"):
            return custom["weights"]
        return None

    def get_default_interview_count(self) -> int:
        """Return the default interview target set during onboarding (default 5)."""
        return int(
            self._ctx.get("research_preferences", {}).get(
                "default_interview_count", 5
            )
            or 5
        )

    def get_preferred_methods(self) -> List[str]:
        """Return the user's learned/preferred research methods (built up over time)."""
        return (
            self._ctx.get("research_preferences", {}).get("preferred_methods", [])
            or []
        )

    def get_org_context(self) -> Dict:
        """Return the organisation sub-dict from the user profile {type, size, regions}."""
        return self._ctx.get("profile", {}).get("organization", {})

    def get_profile(self) -> Dict:
        """Return the full user profile dict {id, name, role, organization}."""
        return self._ctx.get("profile", {})

    # ------------------------------------------------------------------ #
    # Inject context into research plan
    # ------------------------------------------------------------------ #

    def inject_into_plan(self, plan: Dict) -> Dict:
        """
        Enrich a research plan with user-specific context:
        - Prepend custom data sources to data_signals
        - Add known stakeholders to participant list
        - Adjust interview count to user preference
        """
        plan = dict(plan)

        # Inject custom data sources
        custom_sources = self.get_custom_data_sources()
        if custom_sources:
            injected = [
                {
                    "metric": f"Custom data pull: {src}",
                    "source": src,
                    "description": "Your connected system — pull relevant data for this problem",
                    "injected": True,
                }
                for src in custom_sources
            ]
            existing = plan.get("data_signals", [])
            plan["data_signals"] = injected + [
                s for s in existing if not s.get("injected")
            ]

        # Inject known stakeholders
        known = self.get_known_stakeholders()
        if known:
            existing_parts = plan.get("participants", [])
            injected_parts = [
                {
                    "role":    s.get("role", ""),
                    "count":   "1",
                    "access":  s.get("access_level", "Medium").title(),
                    "note":    s.get("notes", "Known contact from your roster"),
                    "primary": False,
                    "known":   True,
                }
                for s in known
            ]
            # Only add if not already represented by role
            existing_roles = {p["role"].lower() for p in existing_parts}
            new_parts = [
                p for p in injected_parts
                if p["role"].lower() not in existing_roles
            ]
            plan["participants"] = existing_parts + new_parts

        # Inject org context note
        org = self.get_org_context()
        if org.get("type"):
            plan["org_context"] = (
                f"{org.get('type', '')} · {org.get('size', '')} · "
                f"{', '.join(org.get('regions', []))}"
            ).strip(" ·")

        return plan

    # ------------------------------------------------------------------ #
    # Similar ideas detection
    # ------------------------------------------------------------------ #

    def find_similar_ideas(self, domain: str, problem: str) -> List[Dict]:
        """
        Return past ideas in the same domain for comparison.
        Used to surface 'You've evaluated this before' alerts.
        """
        return [
            idea for idea in self._ideas
            if idea.get("domain") == domain
        ]

    # ------------------------------------------------------------------ #
    # Phase unlock notifications
    # ------------------------------------------------------------------ #

    def get_unlock_notifications(self) -> List[str]:
        """
        Returns messages about features unlocked at current phase.
        Called once after phase transition.
        """
        phase = self.get_phase()
        msgs = []
        if phase == 1:
            msgs.append("🟣 Phase 1 — Skout is now learning your domain patterns.")
        if phase == 2:
            msgs.append("🔵 Phase 2 — Scoring weight customisation unlocked. Edit `config/user_context.yaml` to tune your scoring.")
            msgs.append("🔵 Phase 2 — Custom data sources and known stakeholders now appear in every research plan.")
        if phase == 3:
            msgs.append("🟢 Phase 3 — Outcome tracking unlocked. Tag your ideas as pursued / abandoned to help Skout calibrate.")
        return msgs

    # ------------------------------------------------------------------ #
    # Ideas history
    # ------------------------------------------------------------------ #

    def get_ideas_history(self) -> List[Dict]:
        """Return all submitted ideas, most recent first."""
        return list(reversed(self._ideas))   # most recent first

    def get_stats(self) -> Dict:
        """
        Return aggregate statistics over all submitted ideas.

        Returns:
            Dict with keys: total, high_priority (score ≥ 80), avg_score,
            researched (research plans completed), top_domain (most-used domain label).
        """
        ideas = self._ideas
        if not ideas:
            return {"total": 0, "high_priority": 0, "researched": 0, "top_domain": "—"}
        scores = [i.get("score", 0) for i in ideas]
        domain_counts = Counter(i.get("domain", "") for i in ideas)
        top = domain_counts.most_common(1)[0][0] if domain_counts else "—"
        return {
            "total":        len(ideas),
            "high_priority": sum(1 for s in scores if s >= 80),
            "avg_score":    round(sum(scores) / len(scores), 1),
            "researched":   self._learning("research_completed"),
            "top_domain":   DOMAIN_LABELS.get(top, top),
        }

    # ------------------------------------------------------------------ #
    # Custom extensions
    # ------------------------------------------------------------------ #

    def get_custom_domains(self) -> List[Dict]:
        """Return the list of user-defined custom domain dicts from custom_extensions.domains."""
        return (
            self._ctx.get("custom_extensions", {}).get("domains", []) or []
        )

    def add_custom_domain(self, domain_id: str, label: str, parent: str,
                          description: str = "") -> None:
        """
        Register a new custom domain extension and persist to user_context.yaml.
        Duplicate domain_ids are silently ignored.

        Args:
            domain_id:   Unique machine-readable ID (e.g. "sustainability").
            label:       Human-readable display name (e.g. "Sustainability & ESG").
            parent:      Parent SCOR domain this extends (e.g. "planning").
            description: Optional short description shown in the UI.
        """
        exts = self._ctx.setdefault("custom_extensions", {})
        domains = exts.setdefault("domains", [])
        # Avoid duplicates
        if not any(d["id"] == domain_id for d in domains):
            domains.append({
                "id": domain_id,
                "label": label,
                "parent": parent,
                "description": description,
            })
        self.save()

    def add_known_stakeholder(self, role: str, access_level: str = "medium",
                              notes: str = "") -> None:
        """
        Add a stakeholder the user has interview access to and persist to YAML.
        Duplicate roles (case-insensitive) are silently ignored.

        Args:
            role:         Stakeholder job title or role (e.g. "VP of Supply Chain").
            access_level: How easily the PM can reach this person: "high" / "medium" / "low".
            notes:        Optional free-text notes (e.g. "prefers async comms").
        """
        prefs = self._ctx.setdefault("research_preferences", {})
        stakeholders = prefs.setdefault("known_stakeholders", [])
        if not any(s.get("role", "").lower() == role.lower() for s in stakeholders):
            stakeholders.append({
                "role":         role,
                "access_level": access_level,
                "notes":        notes,
            })
        self.save()

    def update_scoring_weights(self, weights: Dict) -> None:
        """Phase 2+ — allow user to customise dimension weights."""
        custom = self._ctx.setdefault("scoring_customization", {})
        custom["enabled"] = True
        custom["weights"] = weights
        self.save()

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _learning(self, key: str) -> Any:
        """Read a scalar value from learning_data (returns 0 if absent)."""
        return self._ctx.get("learning_data", {}).get(key, 0)

    def _learning_dict(self, key: str) -> Dict:
        """Read a dict value from learning_data (returns {} if absent or non-dict)."""
        val = self._ctx.get("learning_data", {}).get(key, {})
        return val if isinstance(val, dict) else {}

    def _set_learning(self, key: str, value: Any) -> None:
        """Write a value into the learning_data section of context (in-memory only)."""
        self._ctx.setdefault("learning_data", {})[key] = value

    def _top_domain(self) -> Optional[str]:
        """Return the most frequently evaluated domain, or None if no history exists."""
        dh = self._learning_dict("domain_history")
        if not dh:
            return None
        return max(dh, key=dh.get)
