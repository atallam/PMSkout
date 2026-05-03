"""
BRM Tracker — Phase 4 (Benefits Realisation Management)
Tracks predicted vs actual outcomes per idea.
Persists to data/outcomes.json.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


# ------------------------------------------------------------------ #
# Constants
# ------------------------------------------------------------------ #

BENEFIT_CATEGORIES = [
    "Cost Reduction",
    "Time / Cycle-time Savings",
    "Quality Improvement",
    "Revenue Growth",
    "Risk Reduction",
    "Compliance",
    "Employee Productivity",
]

REALISATION_STATUS = [
    "Tracking",     # idea in flight — capturing predicted benefits
    "Delivered",    # implemented — actual benefits being measured
    "Exceeded",     # actual > predicted by >10%
    "Partial",      # actual < predicted by >20%
    "Abandoned",    # idea was stopped
    "Not Started",  # idea not yet implemented
]

MEASUREMENT_UNITS = [
    "%", "$K", "$M", "hours/week", "days", "FTE", "orders/day", "% accuracy", "custom",
]


# ------------------------------------------------------------------ #
# Data model
# ------------------------------------------------------------------ #

@dataclass
class BenefitItem:
    category: str             # one of BENEFIT_CATEGORIES
    description: str          # what benefit, e.g. "Reduce invoice exception rate"
    predicted_value: float    # numeric predicted benefit
    predicted_unit: str       # unit, e.g. "%" or "$K"
    actual_value: Optional[float] = None
    actual_unit: Optional[str] = None
    measurement_date: Optional[str] = None  # ISO date when actual was measured
    notes: str = ""

    @property
    def realisation_pct(self) -> Optional[float]:
        if self.predicted_value and self.actual_value is not None:
            return round((self.actual_value / self.predicted_value) * 100, 1)
        return None

    def to_dict(self) -> Dict:
        return {
            "category":          self.category,
            "description":       self.description,
            "predicted_value":   self.predicted_value,
            "predicted_unit":    self.predicted_unit,
            "actual_value":      self.actual_value,
            "actual_unit":       self.actual_unit,
            "measurement_date":  self.measurement_date,
            "notes":             self.notes,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "BenefitItem":
        return cls(
            category=d.get("category", ""),
            description=d.get("description", ""),
            predicted_value=float(d.get("predicted_value", 0)),
            predicted_unit=d.get("predicted_unit", "%"),
            actual_value=d.get("actual_value"),
            actual_unit=d.get("actual_unit"),
            measurement_date=d.get("measurement_date"),
            notes=d.get("notes", ""),
        )


@dataclass
class OutcomeRecord:
    idea_title: str
    idea_domain: str
    idea_score: float
    created_date: str                         # ISO date
    status: str = "Not Started"              # one of REALISATION_STATUS
    go_live_date: Optional[str] = None       # ISO date — when idea went live
    review_date: Optional[str] = None        # ISO date — next review
    benefits: List[BenefitItem] = field(default_factory=list)
    milestones: List[Dict] = field(default_factory=list)  # {name, due, done, date_done}
    stakeholder_feedback: str = ""
    lessons_learned: str = ""
    last_updated: str = ""

    @property
    def overall_realisation_pct(self) -> Optional[float]:
        """Average realisation % across all benefits that have actual values."""
        with_actual = [b.realisation_pct for b in self.benefits if b.realisation_pct is not None]
        if not with_actual:
            return None
        return round(sum(with_actual) / len(with_actual), 1)

    @property
    def predicted_total_value(self) -> Dict[str, float]:
        """Sum predicted values grouped by unit."""
        totals: Dict[str, float] = {}
        for b in self.benefits:
            totals[b.predicted_unit] = totals.get(b.predicted_unit, 0) + b.predicted_value
        return totals

    def to_dict(self) -> Dict:
        return {
            "idea_title":           self.idea_title,
            "idea_domain":          self.idea_domain,
            "idea_score":           self.idea_score,
            "created_date":         self.created_date,
            "status":               self.status,
            "go_live_date":         self.go_live_date,
            "review_date":          self.review_date,
            "benefits":             [b.to_dict() for b in self.benefits],
            "milestones":           self.milestones,
            "stakeholder_feedback": self.stakeholder_feedback,
            "lessons_learned":      self.lessons_learned,
            "last_updated":         self.last_updated,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "OutcomeRecord":
        rec = cls(
            idea_title=d.get("idea_title", ""),
            idea_domain=d.get("idea_domain", ""),
            idea_score=float(d.get("idea_score", 0)),
            created_date=d.get("created_date", ""),
            status=d.get("status", "Not Started"),
            go_live_date=d.get("go_live_date"),
            review_date=d.get("review_date"),
            milestones=d.get("milestones", []),
            stakeholder_feedback=d.get("stakeholder_feedback", ""),
            lessons_learned=d.get("lessons_learned", ""),
            last_updated=d.get("last_updated", ""),
        )
        rec.benefits = [BenefitItem.from_dict(b) for b in d.get("benefits", [])]
        return rec


# ------------------------------------------------------------------ #
# BRM Tracker (persistence)
# ------------------------------------------------------------------ #

class BRMTracker:
    """
    Loads, saves, and provides queries over OutcomeRecord objects.
    File: data/outcomes.json  (list of OutcomeRecord.to_dict())
    """

    def __init__(self, data_path: Optional[str] = None):
        if data_path is None:
            data_path = str(Path(__file__).parent.parent / "data" / "outcomes.json")
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

    def _save(self, records: List[Dict]):
        with open(self.data_path, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2, ensure_ascii=False)

    # ── CRUD ───────────────────────────────────────────────────────────

    def get_all(self) -> List[OutcomeRecord]:
        return [OutcomeRecord.from_dict(d) for d in self._load()]

    def get_by_title(self, idea_title: str) -> Optional[OutcomeRecord]:
        for d in self._load():
            if d.get("idea_title", "").strip().lower() == idea_title.strip().lower():
                return OutcomeRecord.from_dict(d)
        return None

    def upsert(self, record: OutcomeRecord):
        """Insert or update a record (matched by idea_title)."""
        record.last_updated = date.today().isoformat()
        records = self._load()
        for i, d in enumerate(records):
            if d.get("idea_title", "").strip().lower() == record.idea_title.strip().lower():
                records[i] = record.to_dict()
                self._save(records)
                return
        records.append(record.to_dict())
        self._save(records)

    def delete(self, idea_title: str) -> bool:
        records = self._load()
        new = [d for d in records if d.get("idea_title", "").strip().lower() != idea_title.strip().lower()]
        if len(new) < len(records):
            self._save(new)
            return True
        return False

    def add_milestone(self, idea_title: str, name: str, due: str):
        record = self.get_by_title(idea_title)
        if record:
            record.milestones.append({"name": name, "due": due, "done": False, "date_done": None})
            self.upsert(record)

    def complete_milestone(self, idea_title: str, milestone_name: str):
        record = self.get_by_title(idea_title)
        if record:
            for m in record.milestones:
                if m["name"] == milestone_name:
                    m["done"] = True
                    m["date_done"] = date.today().isoformat()
            self.upsert(record)

    # ── Analytics ──────────────────────────────────────────────────────

    def portfolio_summary(self) -> Dict[str, Any]:
        records = self.get_all()
        if not records:
            return {}

        status_counts: Dict[str, int] = {}
        for r in records:
            status_counts[r.status] = status_counts.get(r.status, 0) + 1

        delivered = [r for r in records if r.status in ("Delivered", "Exceeded")]
        avg_realisation = None
        if delivered:
            vals = [r.overall_realisation_pct for r in delivered if r.overall_realisation_pct is not None]
            if vals:
                avg_realisation = round(sum(vals) / len(vals), 1)

        return {
            "total":            len(records),
            "status_counts":    status_counts,
            "avg_realisation":  avg_realisation,
            "delivered_count":  len(delivered),
        }

    # ── Scaffold from idea card ─────────────────────────────────────────

    @staticmethod
    def scaffold_from_card(
        idea_title: str,
        idea_domain: str,
        idea_score: float,
        next_actions: Optional[List[str]] = None,
    ) -> OutcomeRecord:
        """
        Create a starter OutcomeRecord from an idea card.
        Adds suggested milestones from next_actions.
        """
        record = OutcomeRecord(
            idea_title=idea_title,
            idea_domain=idea_domain,
            idea_score=idea_score,
            created_date=date.today().isoformat(),
            status="Not Started",
        )
        # Scaffold milestones from next_actions
        if next_actions:
            for action in next_actions[:5]:
                record.milestones.append({
                    "name":      action[:80],
                    "due":       "",
                    "done":      False,
                    "date_done": None,
                })
        return record
