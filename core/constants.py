"""
Skout — Shared Label Dictionaries
Single source of truth for all human-readable label maps used by
research_planner.py, app.py, and any future modules.

Adding a new domain/problem?  Add one entry here — everywhere picks it up.
"""
from __future__ import annotations
from typing import Dict

# ── Problem labels (Q2) ─────────────────────────────────────────────── #
# Maps answer ID → display string used in hypotheses, UI, and plans.
Q2_LABELS: Dict[str, str] = {
    # planning
    "forecast_accuracy":     "forecast accuracy problems",
    "inventory_optimization":"inventory overstock / stockout",
    "sop_process":           "S&OP planning gaps",
    "demand_sensing":        "demand signal quality",
    "capacity_planning":     "capacity planning",
    # procurement
    "supplier_risk":         "supplier risk and visibility gaps",
    "invoice_reconciliation":"invoice matching and reconciliation",
    "contract_compliance":   "contract compliance / spend leakage",
    "po_cycle_time":         "PO approval delays",
    "tail_spend":            "tail spend / maverick buying",
    # repair
    "turnaround_time":       "SLA failures and turnaround delays",
    "parts_availability":    "parts availability shortfalls",
    "warranty_claims":       "warranty claim leakage",
    "cost_per_repair":       "repair cost control",
    "counterfeit_parts":     "parts authenticity / counterfeit risk",
    "reverse_logistics":     "reverse logistics inefficiency",
    # trade
    "customs_delays":        "customs clearance delays and documentation errors",
    "duty_optimization":     "duty and tariff cost optimisation",
    "trade_partner":         "trade partner and broker management",
    # fraud
    "invoice_fraud":         "invoice and payment fraud",
    "supplier_collusion":    "supplier collusion and kickback schemes",
    "internal_controls":     "internal controls gaps and audit failures",
    "warranty_fraud":        "returns and warranty fraud",
    # generic
    "visibility_gaps":       "visibility and data gaps",
    "cost_leakage":          "uncontrolled cost / leakage",
    "process_inefficiency":  "process inefficiency and manual work",
    "compliance_risk":       "compliance and regulatory risk",
    "other":                 "a custom problem",
}

# ── Stakeholder labels (Q3) ─────────────────────────────────────────── #
Q3_LABELS: Dict[str, str] = {
    "sc_planners":       "Supply Chain Planners",
    "procurement_mgrs":  "Procurement / Category Managers",
    "operations":        "Operations and Field Teams",
    "finance":           "Finance and Compliance",
    "leadership":        "Supply Chain Leadership",
    "external_partners": "External Partners and Suppliers",
}

# ── Current-state labels (Q4) ───────────────────────────────────────── #
# Used in hypothesis templates (research_planner) and JTBD statements (app).
Q4_LABELS: Dict[str, str] = {
    "manual_spreadsheet": "manual spreadsheet processes",
    "legacy_erp":         "legacy ERP (SAP / Oracle) that can't solve this",
    "siloed_tools":       "multiple disconnected point solutions",
    "internal_tool":      "an internal tool that doesn't scale",
    "competitor_exists":  "an existing market solution that's inadequate",
    "not_handled":        "no solution — the problem is simply ignored",
}

# ── Frequency labels (Q5.frequency) ─────────────────────────────────── #
FREQ_LABELS: Dict[str, str] = {
    "daily":   "daily",
    "weekly":  "several times a week",
    "monthly": "weekly or monthly",
    "rare":    "quarterly or rarely",
}

# ── Severity labels (Q5.severity) ───────────────────────────────────── #
SEV_LABELS: Dict[str, str] = {
    "stops_work":       "work completely stops",
    "major_workaround": "a major workaround is required",
    "slows_down":       "things are noticeably slowed down",
    "minor":            "minor friction only",
}

# ── Workaround effort labels (Q5.workaround_effort) ─────────────────── #
WK_LABELS: Dict[str, str] = {
    "heavy_manual":        "more than 10 hrs/week of manual effort",
    "dedicated_headcount": "dedicated headcount to manage it",
    "costly_tool":         "an expensive third-party workaround",
    "minimal":             "a minimal / easy workaround",
}

# ── Domain display labels ────────────────────────────────────────────── #
# Used across app.py, user_context_manager.py, and research_planner.py.
DOMAIN_LABELS: Dict[str, str] = {
    "planning":    "Planning & Forecasting",
    "procurement": "Procurement & Sourcing",
    "repair":      "Repair & MRO",
    "trade":       "Trade & Compliance",
    "fraud":       "Fraud & Risk",
}
