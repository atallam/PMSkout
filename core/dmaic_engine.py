"""
DMAIC Engine — Phase 4
Structured problem framing using Define / Measure / Analyze / Improve / Control.
Maps Q1-Q5 answers + research plan into a DMAIC canvas.
Supply Chain domain-aware.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


# ------------------------------------------------------------------ #
# Domain / problem context maps
# ------------------------------------------------------------------ #

_PROBLEM_STATEMENTS: Dict[str, str] = {
    "forecast_accuracy":      "Demand forecasts deviate significantly from actuals, causing inventory imbalances.",
    "inventory_optimization": "Inventory levels (overstock / stockout) are not optimised against service levels.",
    "supplier_lead_time":     "Supplier lead-time variability is causing supply disruptions and expediting costs.",
    "invoice_reconciliation": "Invoice exceptions and mismatches are creating payment delays and audit risk.",
    "po_cycle_time":          "Purchase Order creation-to-approval cycle time exceeds acceptable thresholds.",
    "spend_visibility":       "Procurement spend is fragmented across systems, limiting strategic category decisions.",
    "supplier_onboarding":    "Supplier onboarding takes too long, delaying supply chain ramp-up.",
    "asset_utilization":      "Asset utilisation is below target, increasing cost-per-output and downtime risk.",
    "work_order_completion":  "Work orders are not completed on schedule, impacting equipment availability.",
    "compliance_tracking":    "Trade compliance checks are manual, creating risk of regulatory breaches.",
    "data_quality":           "Supply chain master data has accuracy issues that propagate errors downstream.",
    "other":                  "A supply chain operational problem has been identified that requires structured investigation.",
}

_DOMAIN_SIPOC: Dict[str, Dict] = {
    "planning": {
        "suppliers":  ["Historical sales system", "Demand signals (POS, orders)", "Marketing plan"],
        "inputs":     ["Demand history", "Promotions calendar", "Market intelligence"],
        "process":    ["Statistical baseline → Consensus S&OP → Release plan → Execute"],
        "outputs":    ["Approved demand plan", "Supply requirements", "Inventory targets"],
        "customers":  ["Supply planners", "Procurement", "Manufacturing", "Finance"],
    },
    "procurement": {
        "suppliers":  ["Business users (requisitioners)", "Approved vendor list", "Contract repository"],
        "inputs":     ["Purchase requisitions", "Supplier quotes", "Contract terms"],
        "process":    ["Requisition → Sourcing → PO creation → Receipt → Invoice → Payment"],
        "outputs":    ["Purchase orders", "Goods receipts", "Supplier payments"],
        "customers":  ["Operations", "Finance/AP", "Warehouse"],
    },
    "repair": {
        "suppliers":  ["Maintenance planners", "Asset registry", "Parts warehouse"],
        "inputs":     ["Work requests", "Inspection reports", "Parts availability"],
        "process":    ["Request → Planning → Parts issue → Execution → Close → QA"],
        "outputs":    ["Completed work orders", "Asset health records", "Cost actuals"],
        "customers":  ["Operations", "Asset owners", "Regulatory/HSE"],
    },
    "trade": {
        "suppliers":  ["Customs broker", "Logistics provider", "Compliance team"],
        "inputs":     ["Commercial invoice", "Packing list", "HS codes", "Country of origin"],
        "process":    ["Shipment booking → Documentation → Customs declaration → Clearance → Delivery"],
        "outputs":    ["Cleared shipments", "Duty assessments", "Compliance records"],
        "customers":  ["Procurement", "Warehouse", "Finance"],
    },
    "fraud": {
        "suppliers":  ["ERP/AP system", "Vendor master", "Bank data"],
        "inputs":     ["Transaction records", "Vendor details", "Approval logs"],
        "process":    ["Transaction → Rule-based screening → Anomaly detection → Review → Resolve"],
        "outputs":    ["Cleared transactions", "Flagged cases", "Audit trail"],
        "customers":  ["Finance/AP", "Internal audit", "Compliance"],
    },
}

_DOMAIN_MEASURES: Dict[str, List[str]] = {
    "planning":    ["Forecast MAPE (%)", "Forecast Bias (%)", "Service Level (%)", "Days of Supply", "Inventory Turns"],
    "procurement": ["PO Cycle Time (days)", "Invoice Exception Rate (%)", "3-way Match Rate (%)", "Spend on Contract (%)", "Supplier On-time Delivery (%)"],
    "repair":      ["Work Order On-time Completion (%)", "Mean Time to Repair (hrs)", "Asset Uptime (%)", "Parts Availability (%)", "Backlog (# WOs)"],
    "trade":       ["Customs Clearance Time (days)", "Compliance Exception Rate (%)", "Duty Accuracy (%)", "Shipment On-time Rate (%)"],
    "fraud":       ["False Positive Rate (%)", "Detection Rate (%)", "Mean Time to Resolve (days)", "Value at Risk ($)"],
}

_ROOT_CAUSE_CATEGORIES = [
    "People — skills, training, behaviours",
    "Process — undefined, inconsistent, or manual steps",
    "Technology — system gaps, data quality, integration",
    "Data — accuracy, timeliness, accessibility",
    "Governance — ownership, escalation paths, KPIs",
    "Supplier/partner — external dependencies",
]

_STAKEHOLDER_LABELS = {
    "sc_planners":       "Supply Chain Planners",
    "procurement_mgrs":  "Procurement Managers",
    "finance_analysts":  "Finance Analysts",
    "ops_managers":      "Operations Managers",
    "field_technicians": "Field Technicians",
    "compliance_team":   "Compliance Team",
}

_Q4_LABELS = {
    "manual_spreadsheet": "Manual / spreadsheet-based process",
    "legacy_erp":         "Legacy ERP with limited automation",
    "siloed_tools":       "Siloed point tools (no integration)",
    "competitor_exists":  "A competitor/similar product exists",
    "not_handled":        "Not handled — gap in the market",
    "other":              "Other / unclear",
}

_FREQ_LABELS  = {"daily": "Daily", "weekly": "Weekly", "monthly": "Monthly", "rarely": "Rarely"}
_SEV_LABELS   = {"critical": "Critical", "significant": "Significant", "moderate": "Moderate", "low": "Low"}
_WK_LABELS    = {"high": "High cost/effort", "medium": "Medium effort", "low": "Low effort", "none": "No workaround"}


# ------------------------------------------------------------------ #
# Output model
# ------------------------------------------------------------------ #

@dataclass
class DMAICCanvas:
    idea_title: str
    domain: str

    # D — Define
    problem_statement: str   = ""
    project_scope:     str   = ""
    voice_of_customer: str   = ""  # who suffers, what they want
    sipoc:             Dict  = field(default_factory=dict)  # {suppliers, inputs, process, outputs, customers}
    goal_statement:    str   = ""

    # M — Measure
    baseline_metrics:  List[str]         = field(default_factory=list)
    data_signals:      List[Dict]        = field(default_factory=list)  # from research plan
    measurement_plan:  str               = ""

    # A — Analyze
    root_cause_categories: List[str]     = field(default_factory=list)
    fishbone_branches:     Dict[str, str]= field(default_factory=dict)  # category → hypothesis
    riskiest_assumption:   str           = ""
    counter_arguments:     List[str]     = field(default_factory=list)

    # I — Improve
    solution_direction:   str            = ""
    quick_wins:           List[str]      = field(default_factory=list)
    strategic_changes:    List[str]      = field(default_factory=list)

    # C — Control
    success_criteria:     List[Dict]     = field(default_factory=list)  # from research plan
    control_plan:         str            = ""
    kpi_owners:           str            = ""

    def to_markdown(self) -> str:
        lines = [
            f"# DMAIC Canvas: {self.idea_title}",
            f"**Domain:** {self.domain}",
            "",
            "---",
            "## D — Define",
            f"**Problem Statement:** {self.problem_statement}",
            f"**Scope:** {self.project_scope}",
            f"**Voice of Customer:** {self.voice_of_customer}",
            f"**Goal Statement:** {self.goal_statement}",
            "",
            "### SIPOC",
        ]
        for key in ["suppliers", "inputs", "process", "outputs", "customers"]:
            val = self.sipoc.get(key, [])
            lines.append(f"**{key.title()}:** " + (", ".join(val) if isinstance(val, list) else val))

        lines += [
            "",
            "---",
            "## M — Measure",
            f"**Baseline Metrics:** " + (", ".join(self.baseline_metrics) or "TBD"),
            f"**Measurement Plan:** {self.measurement_plan}",
            "",
            "---",
            "## A — Analyze",
            "**Root Cause Categories:**",
        ]
        for cat in self.root_cause_categories:
            hyp = self.fishbone_branches.get(cat, "")
            lines.append(f"- {cat}" + (f": {hyp}" if hyp else ""))

        if self.riskiest_assumption:
            lines.append(f"\n**Riskiest Assumption:** {self.riskiest_assumption}")

        lines += [
            "",
            "---",
            "## I — Improve",
            f"**Solution Direction:** {self.solution_direction}",
            "**Quick Wins:**",
        ]
        for qw in self.quick_wins:
            lines.append(f"- {qw}")
        lines.append("**Strategic Changes:**")
        for sc in self.strategic_changes:
            lines.append(f"- {sc}")

        lines += [
            "",
            "---",
            "## C — Control",
            "**Success Criteria:**",
        ]
        for c in self.success_criteria:
            lines.append(f"- [{c.get('type','')}] {c.get('criterion','')}")
        lines.append(f"\n**Control Plan:** {self.control_plan}")
        lines.append(f"**KPI Owners:** {self.kpi_owners}")

        return "\n".join(lines)

    def to_dict(self) -> Dict:
        return {
            "idea_title":           self.idea_title,
            "domain":               self.domain,
            "problem_statement":    self.problem_statement,
            "project_scope":        self.project_scope,
            "voice_of_customer":    self.voice_of_customer,
            "sipoc":                self.sipoc,
            "goal_statement":       self.goal_statement,
            "baseline_metrics":     self.baseline_metrics,
            "measurement_plan":     self.measurement_plan,
            "root_cause_categories":self.root_cause_categories,
            "fishbone_branches":    self.fishbone_branches,
            "riskiest_assumption":  self.riskiest_assumption,
            "counter_arguments":    self.counter_arguments,
            "solution_direction":   self.solution_direction,
            "quick_wins":           self.quick_wins,
            "strategic_changes":    self.strategic_changes,
            "success_criteria":     self.success_criteria,
            "control_plan":         self.control_plan,
            "kpi_owners":           self.kpi_owners,
        }


# ------------------------------------------------------------------ #
# Engine
# ------------------------------------------------------------------ #

class DMAICEngine:
    """
    Generates a DMAICCanvas from Q1-Q5 answers + optional research plan data.

    Usage:
        engine = DMAICEngine()
        canvas = engine.build(answers, idea_title, idea_description, research_plan)
    """

    def build(
        self,
        answers: Dict,
        idea_title: str,
        idea_description: str = "",
        research_plan: Optional[Dict] = None,
        verdict_score: float = 0.0,
    ) -> DMAICCanvas:
        domain    = answers.get("q1", "planning")
        problem   = answers.get("q2", "other")
        q2_text   = answers.get("q2_text", "")
        stkholder = answers.get("q3", "")
        q4        = answers.get("q4", "")
        q5        = answers.get("q5", {})

        freq_label = _FREQ_LABELS.get(q5.get("frequency", ""), "")
        sev_label  = _SEV_LABELS.get(q5.get("severity", ""), "")
        wk_label   = _WK_LABELS.get(q5.get("workaround_effort", ""), "")
        sth_label  = _STAKEHOLDER_LABELS.get(stkholder, stkholder)
        q4_label   = _Q4_LABELS.get(q4, q4)

        plan = research_plan or {}

        canvas = DMAICCanvas(idea_title=idea_title, domain=domain)

        # ── D — Define ────────────────────────────────────────────────
        base_ps = _PROBLEM_STATEMENTS.get(problem, _PROBLEM_STATEMENTS["other"])
        if q2_text:
            canvas.problem_statement = q2_text
        else:
            canvas.problem_statement = base_ps

        canvas.project_scope = (
            f"In-scope: {domain.title()} operations affecting {sth_label}. "
            f"Current state: {q4_label}. "
            f"Out-of-scope: changes to upstream ERP configurations or org structure."
        )

        canvas.voice_of_customer = (
            f"{sth_label} experience this problem {freq_label.lower()} "
            f"with {sev_label.lower()} impact. "
            f"Workaround effort: {wk_label.lower()}. "
            f"They want: {idea_description[:200] if idea_description else 'a more efficient process'}."
        )

        canvas.sipoc = _DOMAIN_SIPOC.get(domain, _DOMAIN_SIPOC["planning"])

        canvas.goal_statement = (
            f"Reduce the {problem.replace('_', ' ')} problem for {sth_label} "
            f"by [target %] within [timeframe], "
            f"as evidenced by [primary KPI] moving from [baseline] to [target]."
        )

        # ── M — Measure ───────────────────────────────────────────────
        canvas.baseline_metrics = _DOMAIN_MEASURES.get(domain, [])[:5]
        canvas.data_signals     = plan.get("data_signals", [])[:6]
        canvas.measurement_plan = (
            f"Collect baseline data for: {', '.join(canvas.baseline_metrics[:3])}. "
            f"Data sources: {', '.join(s.get('source','') for s in canvas.data_signals[:3]) or 'ERP / BI system'}. "
            f"Baseline period: last 90 days."
        )

        # ── A — Analyze ───────────────────────────────────────────────
        canvas.root_cause_categories = _ROOT_CAUSE_CATEGORIES
        canvas.fishbone_branches = {
            cat: "" for cat in _ROOT_CAUSE_CATEGORIES
        }
        # Pre-fill the most likely category based on q4
        if q4 == "manual_spreadsheet":
            canvas.fishbone_branches["Process — undefined, inconsistent, or manual steps"] = (
                "Current process relies on manual spreadsheets prone to human error and version conflicts."
            )
            canvas.fishbone_branches["Technology — system gaps, data quality, integration"] = (
                "No system integration between data sources forces manual reconciliation."
            )
        elif q4 == "legacy_erp":
            canvas.fishbone_branches["Technology — system gaps, data quality, integration"] = (
                "Legacy ERP lacks modern APIs and automation capabilities needed for this process."
            )
        elif q4 == "siloed_tools":
            canvas.fishbone_branches["Technology — system gaps, data quality, integration"] = (
                "Point solutions do not share data, creating reconciliation overhead."
            )

        canvas.riskiest_assumption = plan.get("riskiest_assumption", "")
        canvas.counter_arguments   = plan.get("counter_arguments", [])[:3]

        # ── I — Improve ───────────────────────────────────────────────
        canvas.solution_direction = plan.get("hypothesis", idea_description[:300])
        canvas.quick_wins = [
            f"Document and standardise the current {problem.replace('_',' ')} process.",
            f"Identify top 3 root causes via {sth_label} interviews.",
            "Create a single source of truth for baseline metrics.",
        ]
        canvas.strategic_changes = [
            f"Implement automated {problem.replace('_',' ')} solution.",
            f"Integrate data sources to eliminate manual handoffs.",
            "Establish real-time KPI dashboard and alert thresholds.",
        ]

        # ── C — Control ───────────────────────────────────────────────
        canvas.success_criteria = plan.get("success_criteria", [])
        canvas.control_plan = (
            f"Monitor {', '.join(canvas.baseline_metrics[:2])} weekly. "
            f"Escalation path: {sth_label} → Process Owner → Product Manager. "
            f"Review cadence: monthly for first 6 months post-launch."
        )
        canvas.kpi_owners = f"{sth_label} (primary), Supply Chain Ops Lead (secondary)"

        return canvas
