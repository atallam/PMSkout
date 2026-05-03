"""
Action Tracker — Phase 5
Converts research plan next_steps and research_methods into persistent, trackable action items.
Persists to data/actions.json.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional


# ------------------------------------------------------------------ #
# Status constants
# ------------------------------------------------------------------ #

ACTION_STATUSES = ["Todo", "In Progress", "Done", "Blocked", "Skipped"]

ACTION_SOURCES = {
    "research_plan":  "📋 Research Plan",
    "next_steps":     "🎯 Verdict Actions",
    "interview":      "👥 Interview",
    "data_pull":      "📊 Data Pull",
    "manual":         "✏️ Manual",
}


# ------------------------------------------------------------------ #
# Data model
# ------------------------------------------------------------------ #

@dataclass
class ActionItem:
    id: str
    idea_title: str
    title: str
    source: str          # one of ACTION_SOURCES keys
    status: str = "Todo" # one of ACTION_STATUSES
    owner: str = ""
    due_date: str = ""   # ISO date
    created_at: str = "" # ISO date
    completed_at: str = ""
    notes: str = ""
    priority: str = "Medium"  # "High" | "Medium" | "Low"

    @property
    def is_done(self) -> bool:
        return self.status == "Done"

    @property
    def source_label(self) -> str:
        return ACTION_SOURCES.get(self.source, self.source)

    @property
    def priority_icon(self) -> str:
        return {"High": "🔴", "Medium": "🟡", "Low": "🟢"}.get(self.priority, "⚪")

    def to_dict(self) -> Dict:
        return {
            "id":           self.id,
            "idea_title":   self.idea_title,
            "title":        self.title,
            "source":       self.source,
            "status":       self.status,
            "owner":        self.owner,
            "due_date":     self.due_date,
            "created_at":   self.created_at,
            "completed_at": self.completed_at,
            "notes":        self.notes,
            "priority":     self.priority,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "ActionItem":
        return cls(
            id=d.get("id", str(uuid.uuid4())[:8]),
            idea_title=d.get("idea_title", ""),
            title=d.get("title", ""),
            source=d.get("source", "manual"),
            status=d.get("status", "Todo"),
            owner=d.get("owner", ""),
            due_date=d.get("due_date", ""),
            created_at=d.get("created_at", ""),
            completed_at=d.get("completed_at", ""),
            notes=d.get("notes", ""),
            priority=d.get("priority", "Medium"),
        )


# ------------------------------------------------------------------ #
# Tracker (persistence)
# ------------------------------------------------------------------ #

class ActionTracker:
    """
    CRUD operations on action items stored in data/actions.json.

    Usage:
        tracker = ActionTracker()
        actions = tracker.get_for_idea("My Idea")
        tracker.add(action_item)
        tracker.update_status(action_id, "Done")
    """

    def __init__(self, data_path: Optional[str] = None):
        if data_path is None:
            data_path = str(Path(__file__).parent.parent / "data" / "actions.json")
        self.data_path = data_path
        self._ensure_file()

    def _ensure_file(self):
        p = Path(self.data_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        if not p.exists():
            p.write_text("[]", encoding="utf-8")

    def _load(self) -> List[Dict]:
        try:
            with open(self.data_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def _save(self, items: List[Dict]):
        with open(self.data_path, "w", encoding="utf-8") as f:
            json.dump(items, f, indent=2, ensure_ascii=False)

    # ── CRUD ───────────────────────────────────────────────────────────

    def get_all(self) -> List[ActionItem]:
        return [ActionItem.from_dict(d) for d in self._load()]

    def get_for_idea(self, idea_title: str) -> List[ActionItem]:
        return [
            ActionItem.from_dict(d) for d in self._load()
            if d.get("idea_title", "").strip().lower() == idea_title.strip().lower()
        ]

    def add(self, item: ActionItem):
        items = self._load()
        item.created_at = item.created_at or date.today().isoformat()
        items.append(item.to_dict())
        self._save(items)

    def update_status(self, action_id: str, new_status: str, notes: str = "") -> bool:
        items = self._load()
        for item in items:
            if item.get("id") == action_id:
                item["status"] = new_status
                if new_status == "Done":
                    item["completed_at"] = date.today().isoformat()
                if notes:
                    item["notes"] = notes
                self._save(items)
                return True
        return False

    def update_owner(self, action_id: str, owner: str) -> bool:
        items = self._load()
        for item in items:
            if item.get("id") == action_id:
                item["owner"] = owner
                self._save(items)
                return True
        return False

    def update_due_date(self, action_id: str, due_date: str) -> bool:
        items = self._load()
        for item in items:
            if item.get("id") == action_id:
                item["due_date"] = due_date
                self._save(items)
                return True
        return False

    def delete(self, action_id: str) -> bool:
        items = self._load()
        new   = [i for i in items if i.get("id") != action_id]
        if len(new) < len(items):
            self._save(new)
            return True
        return False

    def delete_for_idea(self, idea_title: str):
        items = self._load()
        new   = [i for i in items if i.get("idea_title", "").strip().lower() != idea_title.strip().lower()]
        self._save(new)

    # ── Scaffold from research plan ────────────────────────────────────

    @staticmethod
    def scaffold_from_plan(
        idea_title: str,
        research_plan: Dict,
        verdict_next_steps: Optional[List[str]] = None,
    ) -> List[ActionItem]:
        """
        Convert a research plan into a starter set of ActionItems.
        Does NOT persist — caller must call add() for each item.
        """
        items: List[ActionItem] = []
        today = date.today().isoformat()

        # From verdict next_steps (highest priority)
        for step in (verdict_next_steps or [])[:3]:
            items.append(ActionItem(
                id=str(uuid.uuid4())[:8],
                idea_title=idea_title,
                title=step[:100],
                source="next_steps",
                status="Todo",
                priority="High",
                created_at=today,
            ))

        # From research methods
        for method in research_plan.get("research_methods", [])[:4]:
            method_name = method.get("method", "")
            count       = method.get("count", "")
            priority    = "High" if method.get("priority") == "Primary" else "Medium"
            if method_name:
                items.append(ActionItem(
                    id=str(uuid.uuid4())[:8],
                    idea_title=idea_title,
                    title=f"{method_name}: {count}" if count else method_name,
                    source="research_plan",
                    status="Todo",
                    priority=priority,
                    created_at=today,
                ))

        # Interview actions
        for participant in research_plan.get("participants", [])[:3]:
            role  = participant.get("role", "")
            count = participant.get("count", "")
            if role:
                items.append(ActionItem(
                    id=str(uuid.uuid4())[:8],
                    idea_title=idea_title,
                    title=f"Schedule {count} interview(s) with {role}",
                    source="interview",
                    status="Todo",
                    priority="High",
                    created_at=today,
                ))

        # Data pull actions
        for signal in research_plan.get("data_signals", [])[:3]:
            metric = signal.get("metric", "")
            source = signal.get("source", "")
            if metric:
                items.append(ActionItem(
                    id=str(uuid.uuid4())[:8],
                    idea_title=idea_title,
                    title=f"Pull data: {metric} from {source}",
                    source="data_pull",
                    status="Todo",
                    priority="Medium",
                    created_at=today,
                ))

        return items

    # ── Analytics ──────────────────────────────────────────────────────

    def summary_for_idea(self, idea_title: str) -> Dict[str, Any]:
        actions = self.get_for_idea(idea_title)
        if not actions:
            return {"total": 0, "done": 0, "pct_done": 0}
        done  = sum(1 for a in actions if a.is_done)
        total = len(actions)
        return {
            "total":    total,
            "done":     done,
            "pct_done": round(done / total * 100) if total else 0,
            "overdue":  sum(
                1 for a in actions
                if a.due_date and not a.is_done and a.due_date < date.today().isoformat()
            ),
        }
