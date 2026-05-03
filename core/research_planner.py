"""
Skout — Research Plan Generator  v0.2
Produces domain-aware, adaptive research plans from scored answers.

Phase 1 upgrades:
  - Problem-specific interview questions (Mom Test quality, keyed by domain__problem)
  - Problem-specific data signals keyed by domain__problem
  - Problem-specific success criteria
  - Human-readable labels throughout (not raw IDs)
  - Riskiest assumption + cheapest validation in rule-based mode
  - Richer STANDARD_PROMPT requesting more context from LLM
  - Deep Research mode: competing hypotheses, counter-arguments, second-order effects
"""
from __future__ import annotations
import json
import re
from typing import Any, Dict, List, Optional

import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))

from core.scoring_engine import VerdictResult  # noqa
from llm.base import BaseLLMProvider           # noqa


# ------------------------------------------------------------------ #
# Human-readable label lookup tables
# ------------------------------------------------------------------ #

Q2_LABELS: Dict[str, str] = {
    # planning
    "forecast_accuracy":    "forecast accuracy problems",
    "inventory_optimization":"inventory overstock / stockout",
    "sop_process":          "S&OP planning gaps",
    "demand_sensing":       "demand signal quality",
    "capacity_planning":    "capacity planning",
    # procurement
    "supplier_risk":        "supplier risk and visibility gaps",
    "invoice_reconciliation":"invoice matching and reconciliation",
    "contract_compliance":  "contract compliance / spend leakage",
    "po_cycle_time":        "PO approval delays",
    "tail_spend":           "tail spend / maverick buying",
    # repair
    "turnaround_time":      "SLA failures and turnaround delays",
    "parts_availability":   "parts availability shortfalls",
    "warranty_claims":      "warranty claim leakage",
    "cost_per_repair":      "repair cost control",
    "counterfeit_parts":    "parts authenticity / counterfeit risk",
    "reverse_logistics":    "reverse logistics inefficiency",
    # trade
    "customs_delays":       "customs clearance delays and documentation errors",
    "duty_optimization":    "duty and tariff cost optimisation",
    "trade_partner":        "trade partner and broker management",
    # fraud
    "invoice_fraud":        "invoice and payment fraud",
    "supplier_collusion":   "supplier collusion and kickback schemes",
    "internal_controls":    "internal controls gaps and audit failures",
    "warranty_fraud":       "returns and warranty fraud",
    # generic
    "visibility_gaps":      "visibility and data gaps",
    "cost_leakage":         "uncontrolled cost / leakage",
    "process_inefficiency": "process inefficiency and manual work",
    "compliance_risk":      "compliance and regulatory risk",
    "other":                "a custom problem",
}

Q3_LABELS: Dict[str, str] = {
    "sc_planners":      "Supply Chain Planners",
    "procurement_mgrs": "Procurement / Category Managers",
    "operations":       "Operations and Field Teams",
    "finance":          "Finance and Compliance",
    "leadership":       "Supply Chain Leadership",
    "external_partners":"External Partners and Suppliers",
}

Q4_LABELS: Dict[str, str] = {
    "manual_spreadsheet": "manual spreadsheet processes",
    "legacy_erp":         "legacy ERP (SAP / Oracle) that can't solve this",
    "siloed_tools":       "multiple disconnected point solutions",
    "internal_tool":      "an internal tool that doesn't scale",
    "competitor_exists":  "an existing market solution that's inadequate",
    "not_handled":        "no solution — the problem is simply ignored",
}

FREQ_LABELS: Dict[str, str] = {
    "daily":   "daily",
    "weekly":  "several times a week",
    "monthly": "weekly or monthly",
    "rare":    "quarterly or rarely",
}

SEV_LABELS: Dict[str, str] = {
    "stops_work":        "work completely stops",
    "major_workaround":  "a major workaround is required",
    "slows_down":        "things are noticeably slowed down",
    "minor":             "minor friction only",
}

WK_LABELS: Dict[str, str] = {
    "heavy_manual":       "more than 10 hrs/week of manual effort",
    "dedicated_headcount":"dedicated headcount to manage it",
    "costly_tool":        "an expensive third-party workaround",
    "minimal":            "a minimal / easy workaround",
}


# ------------------------------------------------------------------ #
# Domain hypothesis templates  (use human-readable labels via .format)
# ------------------------------------------------------------------ #

DOMAIN_HYPOTHESES: Dict[str, str] = {
    "planning": (
        "{stakeholder} are struggling with {problem} in their planning workflow, "
        "which occurs {frequency} and results in {severity}. "
        "The current approach — {current_state} — costs {workaround}, "
        "reducing forecast reliability and directly impacting service levels and inventory costs."
    ),
    "procurement": (
        "{stakeholder} face {problem} that occurs {frequency}, "
        "creating a situation where {severity}. "
        "With {current_state} as the status quo, requiring {workaround}, "
        "there is a clear gap between what the business needs and what existing tools deliver."
    ),
    "repair": (
        "Repair and MRO operations experience {problem} on a {frequency} basis, "
        "with consequences where {severity} each time it hits. "
        "Current handling via {current_state} — costing {workaround} — "
        "creates bottlenecks that erode SLA performance and inflate total cost of repair."
    ),
    "trade": (
        "{stakeholder} encounter {problem} with {frequency} regularity, "
        "resulting in situations where {severity}. "
        "Existing processes — {current_state} — demand {workaround} "
        "and leave significant compliance risk and cost unaddressed."
    ),
    "fraud": (
        "Fraud and risk exposure in the form of {problem} is occurring {frequency}, "
        "with consequences where {severity} each incident. "
        "Current controls — {current_state} — require {workaround} "
        "and are insufficient to detect or prevent this at scale."
    ),
}


# ------------------------------------------------------------------ #
# Problem-specific interview questions  (Mom Test quality)
# Key format: "{domain}__{problem_id}"
# Each question follows: Process → Pain → Outcome → History → Risk
# ------------------------------------------------------------------ #

PROBLEM_INTERVIEW_QUESTIONS: Dict[str, List[Dict]] = {

    # ── Planning ──────────────────────────────────────────────────────
    "planning__forecast_accuracy": [
        {"question": "Walk me through your last planning cycle — from when demand data came in to when the plan was locked. Where did things actually slow down or break?",
         "intent": "Process", "intent_desc": "Map the real workflow, not the documented one"},
        {"question": "Tell me about the last time your forecast was significantly off. What happened downstream — inventory, customer service, production?",
         "intent": "Pain", "intent_desc": "Anchor to a real past incident to quantify actual cost"},
        {"question": "How much time do you spend each week overriding or adjusting system-generated forecasts, and what drives those adjustments?",
         "intent": "Pain", "intent_desc": "Override rate is a proxy for distrust in the current system"},
        {"question": "If your forecast accuracy improved by 15–20 percentage points, what's the first decision that would change for you?",
         "intent": "Outcome", "intent_desc": "Forces the interviewee to commit to a measurable outcome"},
        {"question": "What would make you nervous about trusting a new forecast model enough to act on it — especially for high-stakes SKUs?",
         "intent": "Risk", "intent_desc": "Surface trust and adoption blockers before spec is written"},
    ],

    "planning__inventory_optimization": [
        {"question": "Tell me about the last critical stockout you had — what led to it, and what was the downstream impact on customers and the business?",
         "intent": "Process", "intent_desc": "Map real events; quantify cost of stockout"},
        {"question": "What does excess inventory cost you in practice this month or quarter — not in theory, but in real cash or write-offs?",
         "intent": "Pain", "intent_desc": "Forces financial quantification of overstock"},
        {"question": "How are inventory targets set today — who decides, what data is used, and how often is it revisited?",
         "intent": "Process", "intent_desc": "Understand the current decision-making workflow"},
        {"question": "If you could see, right now, which SKUs are likely to stockout or go obsolete in the next 30 days — what would you do with that information?",
         "intent": "Outcome", "intent_desc": "JTBD outcome test — would they actually act on it?"},
        {"question": "Have you tried to optimize inventory levels more systematically — a model, a tool, an external consultant? What happened?",
         "intent": "History", "intent_desc": "Uncover prior attempts and why they failed or stalled"},
    ],

    "planning__sop_process": [
        {"question": "Walk me through your last S&OP cycle — from pre-S&OP to exec sign-off. Where does the process actually break down or become theatrical?",
         "intent": "Process", "intent_desc": "Distinguish the documented S&OP from what really happens"},
        {"question": "What's the most painful part of preparing for an S&OP meeting — what takes the most time and produces the least value?",
         "intent": "Pain", "intent_desc": "Surface the sharpest pain point unprompted"},
        {"question": "How often does your S&OP process result in a decision that actually changes what gets produced or procured?",
         "intent": "Pain", "intent_desc": "Test whether S&OP is driving decisions or just reporting them"},
        {"question": "If all stakeholders showed up to S&OP with the same numbers and a pre-agreed plan — what decisions would you make differently?",
         "intent": "Outcome", "intent_desc": "Quantify the opportunity cost of misalignment"},
        {"question": "What makes your CFO or COO skeptical about investing in S&OP process improvement?",
         "intent": "Risk", "intent_desc": "Understand exec-level adoption blockers"},
    ],

    "planning__demand_sensing": [
        {"question": "Tell me about the last time a demand spike or drop caught your team completely off-guard. What signals existed but weren't being used?",
         "intent": "Process", "intent_desc": "Identify missed signals and the cost of the surprise"},
        {"question": "When you need a faster demand signal than your system provides — what do you actually do? Who do you call or what do you look at?",
         "intent": "Pain", "intent_desc": "Reveals informal workarounds for demand intelligence gaps"},
        {"question": "How far in advance can you currently see a meaningful change in demand, and what would it mean to have that signal 2 weeks earlier?",
         "intent": "Outcome", "intent_desc": "Quantify the value of faster signal"},
        {"question": "Have you experimented with external data sources — weather, POS data, macroeconomic signals — to improve demand sensing? What happened?",
         "intent": "History", "intent_desc": "Uncover prior experiments and barriers to adoption"},
        {"question": "What would make your planning team skeptical about acting on a demand signal from an external or AI source?",
         "intent": "Risk", "intent_desc": "Surface trust and governance blockers"},
    ],

    "planning__capacity_planning": [
        {"question": "Walk me through the last time you faced an unexpected capacity constraint — what happened step by step, and how did you respond?",
         "intent": "Process", "intent_desc": "Map real response workflow and cost of being reactive"},
        {"question": "How often are you surprised by capacity shortfalls, and what does a typical surprise cost you in overtime, expedite freight, or missed commitments?",
         "intent": "Pain", "intent_desc": "Quantify cost of reactive capacity management"},
        {"question": "If you could see capacity risk 6 weeks out instead of 2 weeks — what specific decisions would you make differently?",
         "intent": "Outcome", "intent_desc": "Force commitment to a concrete behavioral change"},
        {"question": "How do capacity decisions get made today — what data is used, how often is it updated, and who has final say?",
         "intent": "Process", "intent_desc": "Understand current decision frequency and data freshness"},
        {"question": "What would stop operations or finance from trusting a capacity planning recommendation from a new system?",
         "intent": "Risk", "intent_desc": "Identify trust and change management barriers"},
    ],

    # ── Procurement ───────────────────────────────────────────────────
    "procurement__supplier_risk": [
        {"question": "Tell me about the last supplier that caused a significant disruption — how did you find out about the problem, and what happened next?",
         "intent": "Process", "intent_desc": "Map actual discovery and response workflow"},
        {"question": "How much time do you spend each week managing supplier issues that you didn't see coming? What does that cost in escalations, expediting, and firefighting?",
         "intent": "Pain", "intent_desc": "Quantify the cost of reactive supplier management"},
        {"question": "What supplier data do you have right now, and what would you need to trust a risk score on a supplier you've worked with for 5 years?",
         "intent": "Pain", "intent_desc": "Test data availability and trust threshold"},
        {"question": "If you knew 4 weeks in advance which suppliers were likely to have performance issues — what would you do with that information?",
         "intent": "Outcome", "intent_desc": "JTBD outcome test — would they act on early warning?"},
        {"question": "Have you tried to build supplier risk monitoring before — scorecards, third-party data, alerts? What worked and what didn't?",
         "intent": "History", "intent_desc": "Uncover prior attempts and why they failed"},
    ],

    "procurement__invoice_reconciliation": [
        {"question": "Take me through what happens the moment you receive an invoice that doesn't match its PO. Who finds it, what's the process, and how long does it actually take?",
         "intent": "Process", "intent_desc": "Map real exception handling workflow end-to-end"},
        {"question": "In a typical month, how many invoices require manual intervention? What's the average resolution time and who gets pulled into each one?",
         "intent": "Pain", "intent_desc": "Quantify volume and blast radius of exceptions"},
        {"question": "What's your invoice-to-PO auto-match rate right now, and how has that trended over the last year?",
         "intent": "Pain", "intent_desc": "Establish current baseline — anchors any future improvement claim"},
        {"question": "If invoice exceptions were automatically routed to the right approver with all the context they needed — what would that change in your week?",
         "intent": "Outcome", "intent_desc": "Classic JTBD outcome framing"},
        {"question": "What would make your AP team and internal auditors comfortable with a system making automatic matching decisions?",
         "intent": "Risk", "intent_desc": "Surface audit, compliance, and trust blockers"},
    ],

    "procurement__contract_compliance": [
        {"question": "Tell me about the last time you discovered significant off-contract or maverick spend — how did you find it, and how long had it been going on?",
         "intent": "Process", "intent_desc": "Anchor to a real instance; test detection latency"},
        {"question": "What percentage of your total spend do you believe is non-compliant right now? How confident are you in that number?",
         "intent": "Pain", "intent_desc": "Reveal both the scale of the problem and measurement gaps"},
        {"question": "When a stakeholder makes a purchase outside of an approved supplier — what actually happens? Is there a consequence?",
         "intent": "Process", "intent_desc": "Test whether enforcement mechanisms exist or are symbolic"},
        {"question": "If every purchase was automatically checked against contract terms in real time — what would your compliance rate look like and what pushback would you get?",
         "intent": "Outcome", "intent_desc": "Test both value and political resistance simultaneously"},
        {"question": "What makes business stakeholders resistant to tighter contract compliance enforcement — is it convenience, process friction, or something else?",
         "intent": "Risk", "intent_desc": "Surface stakeholder resistance to be addressed in go-to-market"},
    ],

    "procurement__po_cycle_time": [
        {"question": "Walk me through a recent PO that got stuck — from requisition to approved. Where did the delay actually come from?",
         "intent": "Process", "intent_desc": "Map the real bottleneck in PO approval"},
        {"question": "What's the average time from requisition to approved PO in your organisation? What's the longest you've seen, and what caused it?",
         "intent": "Pain", "intent_desc": "Quantify the problem; extremes reveal worst-case business impact"},
        {"question": "What happens to procurement requests when approvers are out of office or unresponsive — does business stop, or does it find another way?",
         "intent": "Pain", "intent_desc": "Reveals informal workarounds that signal how bad the pain really is"},
        {"question": "If PO approvals happened in hours instead of days — what's the first downstream thing that would change?",
         "intent": "Outcome", "intent_desc": "Force a concrete outcome commitment"},
        {"question": "What would make your finance and compliance teams nervous about speeding up the PO approval process?",
         "intent": "Risk", "intent_desc": "Surface control and audit concerns upfront"},
    ],

    "procurement__tail_spend": [
        {"question": "Tell me about the last time someone in the business bought something outside of an approved supplier or process. How did you find out?",
         "intent": "Process", "intent_desc": "Test visibility into maverick buying — detection latency matters"},
        {"question": "What percentage of your transactions are tail spend, and how much procurement team time goes into managing it?",
         "intent": "Pain", "intent_desc": "Quantify volume and effort cost of tail spend"},
        {"question": "When a business unit needs something urgently from an unknown supplier — what actually happens, step by step?",
         "intent": "Process", "intent_desc": "Understand the workaround path that bypasses procurement"},
        {"question": "If tail spend was automatically channeled to preferred suppliers and contracts — what would that save you in negotiation overhead and risk exposure?",
         "intent": "Outcome", "intent_desc": "Quantify the financial opportunity of closing the tail spend gap"},
        {"question": "What makes business stakeholders resistant to procurement controls on smaller or ad hoc purchases?",
         "intent": "Risk", "intent_desc": "Understand the convenience vs. compliance tension"},
    ],

    # ── Repair & MRO ─────────────────────────────────────────────────
    "repair__turnaround_time": [
        {"question": "Walk me through a repair job that missed SLA last month — from the service request coming in to final resolution. Where did the time go?",
         "intent": "Process", "intent_desc": "Map real SLA failure workflow end-to-end"},
        {"question": "What are your typical SLA breach rates right now? What's the penalty — financial, contractual, or customer impact?",
         "intent": "Pain", "intent_desc": "Quantify the business cost of SLA failure"},
        {"question": "What are the top 3 reasons jobs miss SLA — and which one is hardest to control today?",
         "intent": "Pain", "intent_desc": "Surface root causes; test whether they're solvable with data or process"},
        {"question": "If your average repair cycle time dropped by 25% — what would that mean for your SLA hit rate and what would you do with the freed capacity?",
         "intent": "Outcome", "intent_desc": "Force a concrete outcome commitment with financial implication"},
        {"question": "What would make field technicians or service managers resistant to a new workflow management or scheduling system?",
         "intent": "Risk", "intent_desc": "Adoption risk from front-line users — often the hardest barrier"},
    ],

    "repair__parts_availability": [
        {"question": "Tell me about the last time a repair job was delayed because a part wasn't available — what happened, how long was the wait, and what was the customer impact?",
         "intent": "Process", "intent_desc": "Anchor to real incident; quantify delay and downstream cost"},
        {"question": "How many open repair jobs are sitting right now waiting on parts? What's the average wait time?",
         "intent": "Pain", "intent_desc": "Current state baseline — makes any future improvement claim concrete"},
        {"question": "When you run out of a critical part, what do you actually do — escalate, source externally, cannibalise another unit?",
         "intent": "Pain", "intent_desc": "Reveal costly workarounds and their frequency"},
        {"question": "If the right parts were available at the right location 95% of the time — what would that do to your first-time fix rate and SLA?",
         "intent": "Outcome", "intent_desc": "JTBD outcome; link parts availability to key performance metric"},
        {"question": "What would make your operations team skeptical about automated parts replenishment recommendations?",
         "intent": "Risk", "intent_desc": "Uncover trust, inventory ownership, and cost control concerns"},
    ],

    "repair__warranty_claims": [
        {"question": "Walk me through how a warranty claim gets processed — from customer submission to approval or rejection. Where does it slow down or leak?",
         "intent": "Process", "intent_desc": "Map claim lifecycle and identify friction points"},
        {"question": "What percentage of warranty claims do you believe are fraudulent, abusive, or outside of policy? How confident are you in that estimate?",
         "intent": "Pain", "intent_desc": "Quantify leakage scale and reveal measurement gaps"},
        {"question": "What's the average time to process a warranty claim today, and what's the customer impact when it takes too long?",
         "intent": "Pain", "intent_desc": "Two-sided pain: leakage and customer experience"},
        {"question": "If you could automatically flag suspicious warranty claims for review — what would that change in terms of leakage and processing time?",
         "intent": "Outcome", "intent_desc": "JTBD outcome framing for fraud detection"},
        {"question": "What would make your customer service team resistant to tighter warranty claim validation — is there concern about customer experience impact?",
         "intent": "Risk", "intent_desc": "Customer-facing teams often resist tighter controls — understand the trade-off"},
    ],

    "repair__cost_per_repair": [
        {"question": "Tell me about a repair category where costs have been creeping up unexpectedly. How did you find out, and what did you do?",
         "intent": "Process", "intent_desc": "Test cost visibility and detection speed"},
        {"question": "Do you know your cost per repair broken down by category, technician, or region? If not — what data would you need to find out?",
         "intent": "Pain", "intent_desc": "Reveal visibility gaps and data availability"},
        {"question": "When a repair comes in 40% over standard cost — does anyone know in real time, or does it surface in a monthly report?",
         "intent": "Pain", "intent_desc": "Test whether cost control is proactive or retrospective"},
        {"question": "If you could see real-time cost variance by repair type and technician — what action would you take first?",
         "intent": "Outcome", "intent_desc": "Test whether they'd actually act on visibility or if cost ownership is unclear"},
        {"question": "What would make field managers or operations teams push back against tighter per-repair cost tracking?",
         "intent": "Risk", "intent_desc": "Cost tracking can feel like surveillance — understand the resistance"},
    ],

    "repair__counterfeit_parts": [
        {"question": "Tell me about the last time your team encountered a suspicious or potentially counterfeit part. How was it identified, and what happened next?",
         "intent": "Process", "intent_desc": "Test existing detection capability and response workflow"},
        {"question": "How confident are you that your parts supply is free of counterfeits right now? What would it take to prove it?",
         "intent": "Pain", "intent_desc": "Surface confidence gaps — high confidence can mask real exposure"},
        {"question": "What's the worst-case consequence of a counterfeit part making it into the field — safety incident, warranty void, regulatory issue?",
         "intent": "Pain", "intent_desc": "Anchor risk to specific consequence to size the problem"},
        {"question": "If you had automatic authenticity verification for every part received — what would change in your receiving and inspection process?",
         "intent": "Outcome", "intent_desc": "JTBD outcome framing"},
        {"question": "What would make your procurement or operations team resistant to adding authenticity checks to the parts receiving process?",
         "intent": "Risk", "intent_desc": "Speed and throughput concerns are typical blockers at receiving"},
    ],

    "repair__reverse_logistics": [
        {"question": "Walk me through what happens when a faulty unit gets returned — from customer collection to final disposition. Where does it break down?",
         "intent": "Process", "intent_desc": "Map real reverse logistics workflow and exception points"},
        {"question": "What percentage of returns create operational exceptions — missing documentation, wrong routing, disputed condition — and what does managing those exceptions cost?",
         "intent": "Pain", "intent_desc": "Quantify the operational overhead of reverse logistics exceptions"},
        {"question": "How long does it take from a unit being returned to it being repaired, redeployed, or scrapped — and what's the cost of that cycle time?",
         "intent": "Pain", "intent_desc": "Quantify asset recovery speed and cost"},
        {"question": "If reverse logistics was fully tracked and automated — what decisions would you make differently about repair prioritisation and parts recovery?",
         "intent": "Outcome", "intent_desc": "Test whether visibility changes decisions, or just reporting"},
        {"question": "What would make your logistics or warehouse team skeptical about a new reverse logistics tracking platform?",
         "intent": "Risk", "intent_desc": "Integration, data entry burden, and trust concerns"},
    ],

    # ── Trade & Compliance ────────────────────────────────────────────

    "trade__customs_delays": [
        {"question": "Tell me about the last shipment that was held at customs — what exactly happened from the moment it was flagged to when it cleared?",
         "intent": "Process", "intent_desc": "Map the real clearance failure workflow, not the documented one"},
        {"question": "How many hours per week does your team spend chasing documentation issues, broker queries, or customs exceptions — and what does that actually cost in staff time and delay penalties?",
         "intent": "Pain", "intent_desc": "Quantify the operational and financial cost of customs friction"},
        {"question": "Which corridors or trade lanes cause the most recurring clearance problems — and do you know why those specific lanes are worse?",
         "intent": "Pain", "intent_desc": "Identify whether the problem is systemic or corridor-specific"},
        {"question": "If customs clearance was predictable and documentation errors dropped by 80% — what would that unlock for you in terms of planning or customer commitments?",
         "intent": "Outcome", "intent_desc": "Force quantification of the business upside of reliable clearance"},
        {"question": "What would concern you about automating or digitising your customs documentation process — especially around regulatory sign-off?",
         "intent": "Risk", "intent_desc": "Surface regulatory, broker-dependency, and audit blockers"},
    ],

    "trade__duty_optimization": [
        {"question": "Walk me through how HS codes are assigned for your top 10 imported product categories — who does it, how often is it reviewed, and what process governs it?",
         "intent": "Process", "intent_desc": "Map current classification governance and identify review gaps"},
        {"question": "Have you ever had a classification review or duty audit that surfaced a material over-payment or mis-classification? What happened and what was the financial impact?",
         "intent": "Pain", "intent_desc": "Anchor to real past event; quantify financial magnitude of the problem"},
        {"question": "What's your current annual duty spend, and do you have any estimate of how much could be recovered or avoided with better classification or FTA utilisation?",
         "intent": "Pain", "intent_desc": "Establish the financial size of the opportunity before investing in research"},
        {"question": "If you had a continuous classification review process — what decisions would change in how you structure trade lanes or source from different origins?",
         "intent": "Outcome", "intent_desc": "Test whether duty optimisation drives strategic decisions, or is just cost recovery"},
        {"question": "What would make your legal or finance team nervous about an automated duty optimisation recommendation — even if it was technically correct?",
         "intent": "Risk", "intent_desc": "Surface audit risk, regulatory liability, and sign-off concerns"},
    ],

    "trade__compliance_risk": [
        {"question": "Describe the last time a regulatory requirement changed and your team had to update processes — how was that handled, and where did it create the most stress?",
         "intent": "Process", "intent_desc": "Map the real change management workflow for regulatory updates"},
        {"question": "How do you currently track which regulations apply to each trade corridor — is that in a system, a spreadsheet, or someone's head?",
         "intent": "Pain", "intent_desc": "Identify whether compliance tracking is systematised or dangerously tribal"},
        {"question": "Has your organisation ever received a regulatory fine or customs penalty? What caused it and what was the total cost — fine plus remediation effort?",
         "intent": "Pain", "intent_desc": "Quantify the real financial downside of compliance gaps"},
        {"question": "If compliance monitoring was automated and you had real-time alerts for regulatory changes affecting your trade lanes — what would you do differently?",
         "intent": "Outcome", "intent_desc": "Test whether real-time monitoring changes decisions or just reduces anxiety"},
        {"question": "What would it take for your legal team to trust an automated compliance system enough to reduce manual review — specifically, what evidence would they need?",
         "intent": "Risk", "intent_desc": "Identify legal team trust barrier and evidence requirements"},
    ],

    "trade__trade_partner": [
        {"question": "Tell me about the last time a broker, freight forwarder, or trade partner created a problem for you — what happened and what did it cost?",
         "intent": "Process", "intent_desc": "Map real partner failure modes and their downstream impact"},
        {"question": "How do you currently assess the performance and reliability of your trade partners — what data do you use and how often do you review it?",
         "intent": "Pain", "intent_desc": "Surface whether performance management is data-driven or relationship-driven"},
        {"question": "If a key trade partner makes a serious error — documentation, routing, mis-classification — how long does it typically take you to detect it and what's the consequence?",
         "intent": "Pain", "intent_desc": "Quantify detection latency and consequence of partner failures"},
        {"question": "If you had full visibility into every trade partner's performance in real time — what decisions would you make differently about partner selection or contract terms?",
         "intent": "Outcome", "intent_desc": "Test whether visibility drives decisions, or just reporting"},
        {"question": "What would make switching to a new broker or trade partner monitoring platform difficult for your operations team?",
         "intent": "Risk", "intent_desc": "Surface change management risk and partner relationship dynamics"},
    ],

    # ── Fraud & Risk ──────────────────────────────────────────────────

    "fraud__invoice_fraud": [
        {"question": "Walk me through what happens when an invoice comes in — from receipt to payment approval. At which step is fraud most likely to slip through?",
         "intent": "Process", "intent_desc": "Map the real AP control workflow and identify the weakest checkpoint"},
        {"question": "Has your organisation ever discovered invoice fraud — either during an audit or by accident? What had been going on, for how long, and what was the total loss?",
         "intent": "Pain", "intent_desc": "Anchor to a real past incident; quantify detection latency and financial loss"},
        {"question": "What percentage of invoices today get flagged for manual review — and of those, how many turn out to be genuinely problematic versus false positives?",
         "intent": "Pain", "intent_desc": "Quantify current false positive rate and the cost of manual review overhead"},
        {"question": "If you had automated fraud detection that flagged suspicious invoices in real time — what would you do differently with that time and that risk information?",
         "intent": "Outcome", "intent_desc": "Test whether real-time detection changes the operating model or just moves work around"},
        {"question": "What would make your finance and legal team comfortable with a system that can automatically hold or flag invoices — without a human approving each flag first?",
         "intent": "Risk", "intent_desc": "Surface legal, audit, and supplier relationship blockers to automation"},
    ],

    "fraud__supplier_collusion": [
        {"question": "How do you currently detect whether a supplier relationship has become too cosy — or whether a procurement team member has a conflict of interest?",
         "intent": "Process", "intent_desc": "Map current collusion detection methods and their real-world effectiveness"},
        {"question": "Has your audit team ever uncovered a kickback scheme or supplier-employee collusion? How long had it been going on before it was caught, and what was the impact?",
         "intent": "Pain", "intent_desc": "Anchor to a real past event to quantify detection latency and financial exposure"},
        {"question": "What data signals do you have today that could indicate unusual supplier concentration, pricing anomalies, or employee-supplier relationships — and are those monitored?",
         "intent": "Pain", "intent_desc": "Identify whether analytics capability exists or if detection is entirely reactive"},
        {"question": "If you had continuous monitoring of supplier award patterns, pricing deviations, and relationship flags — what investigations would you run first?",
         "intent": "Outcome", "intent_desc": "Test whether the team would act on signals, or if cultural/political barriers prevent action"},
        {"question": "What would make procurement leadership or legal counsel nervous about a supplier collusion monitoring tool — even if it surfaces genuine risks?",
         "intent": "Risk", "intent_desc": "Identify political sensitivity, false accusation risk, and legal constraints on evidence use"},
    ],

    "fraud__internal_controls": [
        {"question": "Walk me through how access to payment approval and supplier master data is managed — who has what access, how is it reviewed, and how often?",
         "intent": "Process", "intent_desc": "Map the real access governance process, not just the documented policy"},
        {"question": "When was the last time your organisation did a controls review or segregation-of-duties audit — what did it find and what got fixed?",
         "intent": "Pain", "intent_desc": "Understand the cadence and depth of controls review and whether gaps remain post-audit"},
        {"question": "How long does it typically take to detect a controls violation — and how is it usually discovered? Audit, accident, or tip-off?",
         "intent": "Pain", "intent_desc": "Quantify detection latency and the cost of gaps remaining open"},
        {"question": "If you had real-time controls monitoring that flagged segregation-of-duty violations and unusual access patterns automatically — what would change in how your audit team works?",
         "intent": "Outcome", "intent_desc": "Test whether real-time monitoring changes the audit operating model or just generates more noise"},
        {"question": "What would make IT, finance, and legal hesitant about implementing continuous controls monitoring — particularly around data sensitivity and employee privacy?",
         "intent": "Risk", "intent_desc": "Surface privacy, legal, and IT complexity blockers"},
    ],

    "fraud__warranty_fraud": [
        {"question": "Walk me through what happens when a warranty claim comes in — from submission through to approval or rejection. Where are the controls weakest?",
         "intent": "Process", "intent_desc": "Map the real claims adjudication workflow and identify the gap where abuse enters"},
        {"question": "What's your estimate of the percentage of warranty claims that are abusive, out-of-policy, or fraudulent — and how confident are you in that number?",
         "intent": "Pain", "intent_desc": "Test whether the problem is measured or estimated — and expose how well fraud is understood"},
        {"question": "How do you currently detect patterns of repeat claimants, unusual claim clusters, or out-of-policy submissions — is that systematic or ad hoc?",
         "intent": "Pain", "intent_desc": "Identify whether detection is data-driven or relies on individual intuition"},
        {"question": "If you could detect warranty fraud patterns in real time — which specific claim types or customer segments would you investigate first?",
         "intent": "Outcome", "intent_desc": "Test whether prioritised action is possible, or whether internal politics limit response"},
        {"question": "What would make your customer service or legal team uncomfortable about tightening warranty controls — particularly around false positives and legitimate customer impact?",
         "intent": "Risk", "intent_desc": "Surface the trade-off between fraud reduction and customer experience risk"},
    ],
}


# ------------------------------------------------------------------ #
# Domain-level fallback interview questions  (Mom Test quality)
# Used when no problem-specific questions are available
# ------------------------------------------------------------------ #

DOMAIN_INTERVIEW_QUESTIONS: Dict[str, List[Dict]] = {
    "planning": [
        {"question": "Walk me through your last planning cycle — from receiving the latest demand signal to locking a plan. Where did it actually break down?",
         "intent": "Process", "intent_desc": "Map real workflow, not the documented version"},
        {"question": "Tell me about the last time a planning failure had a real business consequence — what happened and what did it cost?",
         "intent": "Pain", "intent_desc": "Anchor to a specific past incident to quantify impact"},
        {"question": "If this problem was completely gone tomorrow — what's the first decision you'd make differently?",
         "intent": "Outcome", "intent_desc": "JTBD outcome framing — forces commitment to a concrete change"},
        {"question": "Have you tried to fix this before — a tool, a process change, a new hire? What happened?",
         "intent": "History", "intent_desc": "Find prior attempts and why they failed or stalled"},
        {"question": "What would make you nervous about trusting a new planning tool — what would you need to see first?",
         "intent": "Risk", "intent_desc": "Surface adoption blockers before spec is written"},
    ],
    "procurement": [
        {"question": "Take me through a recent procurement problem that cost significant time or money. What happened step by step?",
         "intent": "Process", "intent_desc": "Map real workflow and quantify impact"},
        {"question": "When this problem hits — who else gets pulled in, and how long does it typically take to resolve?",
         "intent": "Pain", "intent_desc": "Quantify workaround effort and blast radius"},
        {"question": "If this problem was completely solved — what would look different in your week?",
         "intent": "Outcome", "intent_desc": "Classic JTBD outcome framing"},
        {"question": "Have you or your team tried to solve this internally — even a spreadsheet or manual process? What happened?",
         "intent": "History", "intent_desc": "Uncover prior attempts and failure modes"},
        {"question": "What data would you need to see from a new tool before you'd trust it with your suppliers and spend?",
         "intent": "Risk", "intent_desc": "Surface data trust and adoption blockers"},
    ],
    "repair": [
        {"question": "Walk me through a recent repair job that didn't go smoothly — from service request to resolution. What caused the friction?",
         "intent": "Process", "intent_desc": "Map real repair workflow end-to-end"},
        {"question": "Where do you lose the most time or cost in a typical repair cycle — and how often does it happen?",
         "intent": "Pain", "intent_desc": "Identify sharpest pain point unprompted"},
        {"question": "If this problem was solved — what would that mean for your SLA performance and cost per repair?",
         "intent": "Outcome", "intent_desc": "Link solution to two key MRO metrics"},
        {"question": "What workarounds does your team use today to cope with this — and what do those workarounds cost?",
         "intent": "History", "intent_desc": "Uncover costly manual coping mechanisms"},
        {"question": "What would make a new repair management tool easy to trust — especially for front-line technicians?",
         "intent": "Risk", "intent_desc": "Adoption risk at the field level"},
    ],
    "trade": [
        {"question": "Describe a recent shipment that got held up in customs or compliance review — what happened and why?",
         "intent": "Process", "intent_desc": "Understand real trade flow friction"},
        {"question": "Which part of your trade compliance process takes the most manual effort each week?",
         "intent": "Pain", "intent_desc": "Surface highest-effort pain point"},
        {"question": "If your clearance time was 40% faster and exceptions dropped by half — what would that mean for the business?",
         "intent": "Outcome", "intent_desc": "Quantify trade delay cost"},
        {"question": "How do you currently manage HS code classification and duty optimisation — broker, internal team, or manual?",
         "intent": "History", "intent_desc": "Understand current state and trust dynamics"},
        {"question": "What would concern you about automating parts of the trade compliance process?",
         "intent": "Risk", "intent_desc": "Identify regulatory and trust blockers"},
    ],
    "fraud": [
        {"question": "Tell me about the last time your team caught a suspicious invoice or payment — how was it caught, and what happened next?",
         "intent": "Process", "intent_desc": "Map current detection workflow"},
        {"question": "How confident are you that your current controls would catch a sophisticated fraud attempt? What makes you say that?",
         "intent": "Pain", "intent_desc": "Surface confidence gaps in current controls"},
        {"question": "If you had real-time fraud alerting across all supplier invoices — what would you do differently?",
         "intent": "Outcome", "intent_desc": "Reveal desired operating model"},
        {"question": "Have you ever found fraud that had been going on for a while before it was detected? What was the impact?",
         "intent": "History", "intent_desc": "Quantify cost of delayed detection"},
        {"question": "What would make your finance and legal teams comfortable with an AI-assisted fraud detection system?",
         "intent": "Risk", "intent_desc": "Surface regulatory and audit blockers"},
    ],
}


# ------------------------------------------------------------------ #
# Problem-specific data signals  (keyed by domain__problem)
# ------------------------------------------------------------------ #

PROBLEM_DATA_SIGNALS: Dict[str, List[Dict]] = {
    "planning__forecast_accuracy": [
        {"metric": "MAPE / WMAPE by SKU category", "source": "Planning system / ERP", "description": "12-month trend — identify which categories are chronically inaccurate"},
        {"metric": "Forecast override rate", "source": "Planning system", "description": "% of system forecasts manually adjusted — high override = low trust in the system"},
        {"metric": "Forecast bias (over vs. under)", "source": "ERP / planning system", "description": "Systematic bias is more expensive than random error — reveals directional failure mode"},
        {"metric": "Stockout incidents linked to forecast miss", "source": "ERP / customer service tickets", "description": "Revenue and service impact of forecast-driven stockouts — the business cost of the problem"},
    ],
    "planning__inventory_optimization": [
        {"metric": "Days on hand by SKU category", "source": "ERP / WMS", "description": "Compare vs. target; identify chronic overstock categories and tied-up cash"},
        {"metric": "Stockout rate and order fill rate", "source": "ERP / OMS", "description": "% of orders fulfilled on time from available stock — the service impact metric"},
        {"metric": "Inventory write-off / obsolescence cost", "source": "Finance / ERP", "description": "Annual cost of inventory that aged out — by category and location"},
        {"metric": "Emergency / expedite freight spend", "source": "Logistics / finance", "description": "Cost of urgent shipments caused by stockouts — proxy for planning failure cost"},
    ],
    "planning__sop_process": [
        {"metric": "S&OP cycle time (demand review to exec sign-off)", "source": "Internal process data / calendar", "description": "Time from first pre-S&OP to locked plan — compare actual vs. intended"},
        {"metric": "Plan change rate post-S&OP", "source": "ERP / planning system", "description": "% of plans revised after sign-off — high rate signals S&OP isn't driving real alignment"},
        {"metric": "Forecast accuracy vs. S&OP baseline", "source": "Planning system", "description": "Does the S&OP process improve forecast accuracy? Compare against naive baseline"},
        {"metric": "Number of S&OP pre-meetings and prep hours", "source": "Calendar / time tracking", "description": "Hidden cost of the S&OP process — prep time is often 10x the meeting time"},
    ],
    "procurement__supplier_risk": [
        {"metric": "Supplier on-time delivery rate by tier", "source": "ERP / supplier portal", "description": "By supplier, category, and tier — trend over 12 months"},
        {"metric": "Supplier quality defect rate", "source": "Quality management system / ERP", "description": "PPM or defect rate by supplier — signals reliability degradation early"},
        {"metric": "Single-source supplier exposure", "source": "Procurement system / spend analysis", "description": "% of critical spend with no approved alternative — concentration risk"},
        {"metric": "Escalations and expedite orders linked to supplier failure", "source": "ERP / procurement", "description": "Count and cost of reactive measures driven by supplier underperformance"},
    ],
    "procurement__invoice_reconciliation": [
        {"metric": "Invoice-to-PO auto-match rate", "source": "ERP / AP system", "description": "% matched without human intervention — last 90 days; trend over 12 months"},
        {"metric": "Invoice exception volume and resolution time", "source": "AP system", "description": "Count of exceptions per month, average days to resolve, and who handles them"},
        {"metric": "Invoice processing cost per transaction", "source": "Finance / AP", "description": "Total AP headcount cost / invoices processed — benchmark against industry: $5–$15 manual vs. $0.50 automated"},
        {"metric": "Duplicate payment rate", "source": "Finance / audit", "description": "Instances of duplicate payments caught (and missed) — last 12 months"},
    ],
    "procurement__po_cycle_time": [
        {"metric": "PO cycle time (requisition to approval)", "source": "ERP / procurement system", "description": "Average and P90 by spend category and approver — P90 reveals worst-case friction"},
        {"metric": "PO backlog and aging", "source": "Procurement system", "description": "Requisitions pending approval > 3 days, > 7 days — how large is the queue?"},
        {"metric": "Approval SLA breach rate", "source": "Procurement system", "description": "% of POs not approved within target SLA — by approver and business unit"},
        {"metric": "Emergency / expedite purchase rate", "source": "ERP / procurement", "description": "% of purchases tagged urgent or expedited — proxy for how often slow PO process causes downstream pain"},
    ],
    "repair__turnaround_time": [
        {"metric": "Mean time to repair (MTTR)", "source": "ITSM / field service system", "description": "By repair type, technician, region — trend over 12 months"},
        {"metric": "SLA breach rate and penalty cost", "source": "ITSM / contracts", "description": "% of jobs breaching SLA, and total penalty payments — the financial cost of slow repair"},
        {"metric": "First-time fix rate", "source": "Field service system", "description": "% of repair jobs resolved on first visit — low rate often signals parts or skills mismatch"},
        {"metric": "Repair backlog aging", "source": "ITSM / work order system", "description": "Jobs open > 3 days, > 7 days, > 14 days — reveals structural capacity or parts constraints"},
    ],
    "repair__parts_availability": [
        {"metric": "Parts availability / fill rate", "source": "Spare parts system / WMS", "description": "% of parts requests fulfilled without delay — by part category and location"},
        {"metric": "Repair jobs delayed by parts", "source": "ITSM / work order system", "description": "Count and average delay time of jobs held waiting on parts"},
        {"metric": "Emergency / expedite parts procurement cost", "source": "ERP / procurement", "description": "Cost of urgent parts sourcing — proxy for stockout frequency and impact"},
        {"metric": "Parts obsolescence and dead stock cost", "source": "Finance / WMS", "description": "Annual write-off of spare parts that aged out — balanced against availability risk"},
    ],
    "repair__warranty_claims": [
        {"metric": "Warranty claim approval rate and trend", "source": "Claims management system", "description": "% approved vs. rejected — and trend; sudden approval rate spike may signal control weakness"},
        {"metric": "Average claim processing time", "source": "Claims system / ITSM", "description": "Time from submission to final decision — impacts customer experience and cash flow"},
        {"metric": "Claim exception and dispute rate", "source": "Claims system", "description": "% of claims requiring manual review — signals where automation could help or controls are weak"},
        {"metric": "Warranty cost as % of product revenue", "source": "Finance", "description": "Benchmark: 1–3% is typical; above 5% signals significant control or product quality issue"},
    ],

    # ── Trade & Compliance ────────────────────────────────────────────

    "trade__customs_delays": [
        {"metric": "Average customs clearance time by trade lane", "source": "Trade management system / broker data", "description": "Average and P90 — identify which corridors are chronically slow; benchmark against industry norms (air 1–2 days, ocean 3–7 days)"},
        {"metric": "Documentation error / exception rate", "source": "Customs broker / trade ops", "description": "% of shipments requiring manual correction — high rate signals broken data flows upstream"},
        {"metric": "Demurrage and detention costs", "source": "Finance / freight invoices", "description": "Cost of delays at port — direct financial evidence of the problem's magnitude"},
        {"metric": "Customs holds by reason code", "source": "Broker / customs agency portal", "description": "Breakdown by reason (missing doc, classification query, physical inspection) — reveals the root cause distribution"},
    ],

    "trade__duty_optimization": [
        {"metric": "Total annual duty and tariff spend", "source": "Finance / customs system", "description": "Last 12 months — establish the baseline opportunity size before evaluating classification improvements"},
        {"metric": "Free Trade Agreement (FTA) utilisation rate", "source": "Trade management system / broker", "description": "% of eligible shipments claiming FTA preferential rates — under-utilisation directly quantifies the savings gap"},
        {"metric": "HS code classification review frequency", "source": "Trade compliance team", "description": "How often product classifications are reviewed — infrequent review is a proxy for classification risk"},
        {"metric": "Duty recovery from prior-period audits", "source": "Finance / customs audit records", "description": "$ recovered in past 3 years from reclassification or drawback claims — proves the financial upside exists"},
    ],

    "trade__compliance_risk": [
        {"metric": "Open regulatory compliance exceptions", "source": "Trade compliance / audit system", "description": "Count and age of unresolved exceptions — older gaps signal systemic weakness, not one-off issues"},
        {"metric": "Regulatory change notifications received vs. processed", "source": "Compliance team records", "description": "How many regulatory updates were received last year, and how many triggered documented process changes"},
        {"metric": "Trade compliance fines and penalties", "source": "Finance / legal records", "description": "Last 3 years — direct financial evidence of the cost of compliance failure"},
        {"metric": "Manual compliance check volume per week", "source": "Trade ops team", "description": "Hours spent on manual compliance checks — quantifies the cost of not having a systematic monitoring tool"},
    ],

    "trade__trade_partner": [
        {"metric": "Partner on-time and error-free shipment rate", "source": "Trade management system / broker scorecards", "description": "By partner — identify which brokers or forwarders are the chronic underperformers"},
        {"metric": "Exceptions attributable to partner errors", "source": "Trade ops exception log", "description": "% of documentation and clearance failures traceable to partner action or inaction"},
        {"metric": "Partner review and re-tendering frequency", "source": "Procurement / trade ops", "description": "How often partner contracts are reviewed — low frequency means poor performance often persists unchallenged"},
        {"metric": "Cost of partner error remediation", "source": "Finance / trade ops", "description": "Staff time plus penalties and re-work costs — builds the business case for partner performance management"},
    ],

    # ── Fraud & Risk ──────────────────────────────────────────────────

    "fraud__invoice_fraud": [
        {"metric": "Invoice exception and hold rate", "source": "AP / ERP system", "description": "% of invoices flagged for manual review — and what % turn out to be genuine issues vs. false positives"},
        {"metric": "Duplicate payment rate", "source": "Finance / AP audit", "description": "Instances of duplicate payments identified last 12 months — benchmark: >0.1% of invoice volume signals weak controls"},
        {"metric": "Average invoice processing time", "source": "AP system", "description": "Longer cycle times increase fraud exposure window — and signal manual overhead ripe for automation"},
        {"metric": "Supplier master data change frequency", "source": "ERP / master data team", "description": "# of bank account or address changes per month — sudden spikes are a classic fraud signal"},
    ],

    "fraud__supplier_collusion": [
        {"metric": "Single-bid and sole-source award rate", "source": "Procurement / sourcing system", "description": "% of contracts awarded without competitive process — elevated rate is a collusion risk indicator"},
        {"metric": "Supplier concentration by buyer", "source": "Spend analytics", "description": "Top 5 spend per buyer — unusual concentration in one buyer-supplier relationship warrants investigation"},
        {"metric": "Price variance to market or contract", "source": "Spend analytics / ERP", "description": "Suppliers pricing consistently above market or above contracted rates — especially for sole-source items"},
        {"metric": "Employee-supplier relationship disclosures", "source": "HR / procurement compliance", "description": "Logged conflicts of interest — zero disclosures in a large team is often a control gap, not clean hands"},
    ],

    "fraud__internal_controls": [
        {"metric": "Segregation of duties (SoD) violations", "source": "ERP access control / audit tool", "description": "Count of active SoD conflicts — any user with both create-supplier and approve-payment access is a critical gap"},
        {"metric": "Privileged access review cadence", "source": "IT / ERP access management", "description": "How often privileged accounts are reviewed and recertified — annual is insufficient; quarterly is minimum best practice"},
        {"metric": "Audit finding remediation rate", "source": "Internal audit tracker", "description": "% of prior-year audit findings fully remediated — low rate signals governance issues beyond tool capability"},
        {"metric": "Controls testing coverage", "source": "Internal audit", "description": "% of key controls tested last year — gaps in testing coverage reveal blind spots in the current framework"},
    ],

    "fraud__warranty_fraud": [
        {"metric": "Warranty claim approval rate and trend", "source": "Claims management system", "description": "% approved vs. rejected over last 12 months — sudden shifts in approval rate signal either policy change or controls weakness"},
        {"metric": "Repeat claimant rate", "source": "Claims system / CRM", "description": "% of claims from customers or partners with 3+ claims in 12 months — elevated rate is a primary fraud signal"},
        {"metric": "Out-of-warranty or out-of-policy claim rate", "source": "Claims system", "description": "% of claims approved despite being technically ineligible — quantifies the leakage from manual override or weak eligibility checks"},
        {"metric": "Warranty cost as % of product revenue", "source": "Finance", "description": "Benchmark: 1–3% is typical for most hardware products; above 5% is a strong signal of fraud or product quality issues requiring investigation"},
    ],
}


# ------------------------------------------------------------------ #
# Domain-level fallback data signals
# ------------------------------------------------------------------ #

DOMAIN_DATA_SIGNALS: Dict[str, List[Dict]] = {
    "planning": [
        {"metric": "Forecast accuracy (MAPE/WMAPE)", "source": "ERP / planning system", "description": "Trend over last 12 months — by SKU category"},
        {"metric": "Inventory turns & days on hand", "source": "ERP / WMS", "description": "By SKU category — compare vs. target"},
        {"metric": "S&OP cycle time", "source": "Internal process data", "description": "Time from demand signal to plan confirmation"},
        {"metric": "Stockout incidents", "source": "ERP / customer service tickets", "description": "Frequency and customer impact"},
    ],
    "procurement": [
        {"metric": "Invoice-to-PO match rate", "source": "ERP / AP system", "description": "% auto-matched vs. exceptions — last 90 days"},
        {"metric": "PO cycle time (requisition to approval)", "source": "ERP / procurement system", "description": "Average and P90"},
        {"metric": "Contract compliance rate", "source": "Spend analytics", "description": "% spend on contract vs. maverick"},
        {"metric": "Supplier on-time delivery rate", "source": "ERP / supplier portal", "description": "By category and supplier tier"},
    ],
    "repair": [
        {"metric": "Mean time to repair (MTTR)", "source": "ITSM / field service system", "description": "By repair type and region"},
        {"metric": "Parts availability rate", "source": "Spare parts / WMS", "description": "% orders fulfilled without delay"},
        {"metric": "Cost per repair", "source": "ERP / work order system", "description": "Trend and breakdown by category"},
        {"metric": "SLA breach rate", "source": "ITSM / service desk", "description": "By customer tier and contract type"},
    ],
    "trade": [
        {"metric": "Customs clearance time", "source": "Trade management system / broker data", "description": "Average and P90 by corridor"},
        {"metric": "Duty paid vs. optimised", "source": "Finance / customs system", "description": "Opportunity to reduce via classification review"},
        {"metric": "Compliance exception rate", "source": "Audit / compliance system", "description": "Regulatory flags raised per quarter"},
        {"metric": "Documentation error rate", "source": "Trade ops team", "description": "% shipments with documentation issues"},
    ],
    "fraud": [
        {"metric": "Invoice exception rate", "source": "AP / ERP system", "description": "Flagged invoices vs. total processed"},
        {"metric": "Duplicate payment rate", "source": "Finance / audit", "description": "Instances caught — and missed — last 12 months"},
        {"metric": "Warranty claim approval rate", "source": "Claims management system", "description": "Approve/reject trend and anomalies"},
        {"metric": "Supplier audit findings", "source": "Procurement / audit team", "description": "Number and severity of control gaps"},
    ],
}


# ------------------------------------------------------------------ #
# Problem-specific success criteria
# ------------------------------------------------------------------ #

PROBLEM_SUCCESS_CRITERIA: Dict[str, List[Dict]] = {
    "planning__forecast_accuracy": [
        {"criterion": "At least 3 planners independently describe the same root cause of forecast error (system trust, data quality, process lag, or external volatility)", "type": "Confirmed"},
        {"criterion": "MAPE data retrieved that quantifies current error rate and at least one category where it is worst", "type": "Quantified"},
        {"criterion": "At least one planner can articulate what decision they would make differently with 15% better accuracy", "type": "Confirmed"},
        {"criterion": "At least one adoption blocker identified (IT integration, model trust, process change resistance)", "type": "Blocker"},
    ],
    "procurement__invoice_reconciliation": [
        {"criterion": "At least 3 AP or procurement staff independently describe the same exception handling pain point", "type": "Confirmed"},
        {"criterion": "Invoice exception volume and average resolution time retrieved from AP system", "type": "Quantified"},
        {"criterion": "Hypothesis about primary cause of mismatches (price, quantity, or master data) confirmed or disproved with data", "type": "Disproved"},
        {"criterion": "Audit / compliance team concern about automated matching identified and scoped", "type": "Blocker"},
    ],
    "procurement__supplier_risk": [
        {"criterion": "At least 3 procurement managers describe supplier disruption as occurring more than monthly", "type": "Confirmed"},
        {"criterion": "At least one instance of supplier disruption cost quantified (expedite, penalty, lost revenue)", "type": "Quantified"},
        {"criterion": "Data on supplier OTD and quality rates retrieved for at least the top 10 suppliers", "type": "Quantified"},
        {"criterion": "Primary blocker to adopting a risk score system identified (data availability, trust, IT, or process)", "type": "Blocker"},
    ],
    "repair__turnaround_time": [
        {"criterion": "At least 3 service managers describe the same root cause of SLA breaches independently", "type": "Confirmed"},
        {"criterion": "MTTR data and SLA breach rate retrieved from ITSM system", "type": "Quantified"},
        {"criterion": "At least one SLA breach cost quantified (penalty payment or customer churn linked to downtime)", "type": "Quantified"},
        {"criterion": "Front-line technician adoption concern identified and scoped", "type": "Blocker"},
    ],
    "repair__parts_availability": [
        {"criterion": "At least 3 technicians or depot managers independently describe parts wait as the primary cause of repair delays", "type": "Confirmed"},
        {"criterion": "Parts fill rate and average parts wait time retrieved from spare parts system", "type": "Quantified"},
        {"criterion": "At least one category of parts identified as chronically unavailable, with frequency and delay duration", "type": "Quantified"},
        {"criterion": "Inventory ownership concern (who pays for higher stock levels?) identified as a potential blocker", "type": "Blocker"},
    ],

    # ── Trade & Compliance ────────────────────────────────────────────

    "trade__customs_delays": [
        {"criterion": "At least 3 trade operations or compliance staff independently identify the same root cause of clearance delays (documentation errors, HS classification queries, or broker failures)", "type": "Confirmed"},
        {"criterion": "Average clearance time and P90 retrieved for at least 2 major trade corridors, with demurrage/detention cost estimate", "type": "Quantified"},
        {"criterion": "Hypothesis about primary delay driver (documentation vs. classification vs. inspection) confirmed or disproved with broker exception data", "type": "Disproved"},
        {"criterion": "Broker dependency or regulatory sign-off constraint identified as a potential blocker to process change", "type": "Blocker"},
    ],

    "trade__duty_optimization": [
        {"criterion": "Total annual duty spend retrieved and at least one product category identified as potentially mis-classified or FTA-ineligible", "type": "Quantified"},
        {"criterion": "At least 2 trade compliance managers confirm classification is reviewed infrequently or lacks formal governance", "type": "Confirmed"},
        {"criterion": "FTA utilisation rate retrieved — hypothesis about under-utilisation confirmed or disproved", "type": "Disproved"},
        {"criterion": "Legal or finance team concern about audit liability from reclassification identified and scoped", "type": "Blocker"},
    ],

    "trade__compliance_risk": [
        {"criterion": "At least 3 compliance or trade operations staff independently describe the same regulatory monitoring gap", "type": "Confirmed"},
        {"criterion": "At least one instance of compliance fine, penalty, or near-miss quantified with financial impact", "type": "Quantified"},
        {"criterion": "Manual compliance check volume quantified (hours/week) to establish automation ROI baseline", "type": "Quantified"},
        {"criterion": "Legal team evidence requirement for trusting automated compliance monitoring identified and scoped", "type": "Blocker"},
    ],

    "trade__trade_partner": [
        {"criterion": "At least 2 trade operations managers independently name the same broker or partner as the primary source of errors", "type": "Confirmed"},
        {"criterion": "Partner error rate and cost of remediation retrieved or estimated from trade ops exception log", "type": "Quantified"},
        {"criterion": "Hypothesis about whether performance management tools exist (vs. relationship-only management) confirmed with evidence", "type": "Disproved"},
        {"criterion": "Contract or relationship lock-in with underperforming partners identified as a potential blocker", "type": "Blocker"},
    ],

    # ── Fraud & Risk ──────────────────────────────────────────────────

    "fraud__invoice_fraud": [
        {"criterion": "At least 3 AP or finance staff independently describe the same control gap in the invoice approval workflow", "type": "Confirmed"},
        {"criterion": "Invoice exception rate and at least one duplicate payment or fraud instance quantified with financial loss", "type": "Quantified"},
        {"criterion": "Hypothesis about whether the problem is volume-driven (manual review overload) vs. controls-driven confirmed with data", "type": "Disproved"},
        {"criterion": "Finance and legal team requirement for human oversight of automated fraud flags identified and scoped", "type": "Blocker"},
    ],

    "fraud__supplier_collusion": [
        {"criterion": "At least 2 internal audit or procurement compliance staff confirm that supplier concentration or single-bid awards are not currently monitored analytically", "type": "Confirmed"},
        {"criterion": "At least one past collusion or conflict-of-interest case identified, with detection lag and financial impact quantified", "type": "Quantified"},
        {"criterion": "Hypothesis about whether spend data is sufficient to surface anomalies confirmed or data gap identified", "type": "Disproved"},
        {"criterion": "Political sensitivity around supplier investigations identified — specifically, whether procurement leadership would act on automated flags", "type": "Blocker"},
    ],

    "fraud__internal_controls": [
        {"criterion": "At least 2 internal audit or ERP access management staff independently confirm active SoD violations exist and are not being remediated at pace", "type": "Confirmed"},
        {"criterion": "Count of open SoD violations and last access review date retrieved from ERP or audit tool", "type": "Quantified"},
        {"criterion": "Hypothesis about whether the problem is governance (policy exists but isn't enforced) vs. tooling (no way to detect violations) confirmed", "type": "Disproved"},
        {"criterion": "IT and legal concern about employee privacy and data sensitivity in continuous controls monitoring identified and scoped", "type": "Blocker"},
    ],

    "fraud__warranty_fraud": [
        {"criterion": "At least 3 claims operations or finance staff independently estimate the fraud rate and agree it is material (>2% of claim volume)", "type": "Confirmed"},
        {"criterion": "Warranty cost as % of revenue and repeat claimant rate retrieved — compared to industry benchmark", "type": "Quantified"},
        {"criterion": "Hypothesis about whether fraud is concentrated in a specific channel, product, or geography confirmed or disproved with claims data", "type": "Disproved"},
        {"criterion": "Customer service team concern about false positives impacting legitimate customers identified and scoped", "type": "Blocker"},
    ],
}

# Default success criteria (used when no problem-specific set is available)
DEFAULT_SUCCESS_CRITERIA: List[Dict] = [
    {"criterion": "At least 3 of 5 interviewees describe the same root cause independently — unprompted", "type": "Confirmed"},
    {"criterion": "At least one data signal retrieved that quantifies frequency, workaround cost, or financial impact", "type": "Quantified"},
    {"criterion": "Primary hypothesis either confirmed or explicitly disproved — no ambiguous outcome", "type": "Disproved"},
    {"criterion": "At least one adoption blocker identified (technical, process, political, or trust-based)", "type": "Blocker"},
]


# ------------------------------------------------------------------ #
# Stakeholder access metadata
# ------------------------------------------------------------------ #

STAKEHOLDER_ACCESS: Dict[str, Dict] = {
    "sc_planners":      {"access": "Medium", "note": "Busy during month-end close and S&OP cycles — schedule around these"},
    "procurement_mgrs": {"access": "Medium", "note": "Easier to reach via procurement head or category lead than cold outreach"},
    "operations":       {"access": "Hard",   "note": "Field staff are hard to reach — use service managers or team leads as proxies"},
    "finance":          {"access": "Easy",   "note": "Usually accessible via business partner or FP&A lead"},
    "leadership":       {"access": "Hard",   "note": "Target VPs/directors first, not C-suite — use your sponsor to gain access"},
    "external_partners":{"access": "Very Hard", "note": "Requires commercial relationship — use key account manager as entry point"},
}

SECONDARY_PARTICIPANTS: Dict[str, List[Dict]] = {
    "planning": [
        {"role": "S&OP Process Owner / COE Lead", "count": "1–2", "access": "Medium",
         "note": "Understands cross-functional dependencies and process constraints"},
        {"role": "IT / ERP System Owner", "count": "1", "access": "Easy",
         "note": "Technical feasibility, data availability, and integration constraints"},
    ],
    "procurement": [
        {"role": "Finance / AP Team Lead", "count": "2–3", "access": "Easy",
         "note": "Downstream impact — payment delays, audit exposure, and reconciliation cost"},
        {"role": "IT / ERP System Owner", "count": "1", "access": "Easy",
         "note": "Technical feasibility and integration with AP / procurement system"},
    ],
    "repair": [
        {"role": "Field Service Manager / Depot Lead", "count": "2–3", "access": "Medium",
         "note": "Operational context for technician workflow and SLA accountability"},
        {"role": "Parts / Inventory Controller", "count": "1–2", "access": "Easy",
         "note": "Spare parts availability, ordering process, and stocking policy"},
    ],
    "trade": [
        {"role": "Customs Broker / Trade Compliance Manager", "count": "1–2", "access": "Medium",
         "note": "External perspective on where delays and documentation errors originate"},
        {"role": "Finance / Duty Manager", "count": "1", "access": "Easy",
         "note": "Duty optimisation opportunity and cost of compliance exceptions"},
    ],
    "fraud": [
        {"role": "Internal Audit Lead", "count": "1–2", "access": "Easy",
         "note": "Understands current control gaps and audit trail requirements"},
        {"role": "IT Security / ERP Access Control Owner", "count": "1", "access": "Easy",
         "note": "Technical constraints on fraud detection implementation"},
    ],
}


# ------------------------------------------------------------------ #
# Research methods by domain
# ------------------------------------------------------------------ #

RESEARCH_METHODS: Dict[str, List[Dict]] = {
    "planning": [
        {"method": "User Interviews", "priority": "Primary", "count": "5–7",
         "rationale": "Map real planning workflows and surface undocumented pain points"},
        {"method": "Process Observation", "priority": "Secondary", "count": "1–2",
         "rationale": "Shadow a planner during S&OP cycle — see what actually happens vs. the documented process"},
        {"method": "Data Pull (ERP)", "priority": "Validation", "count": "90-day dataset",
         "rationale": "Quantify forecast accuracy, exception rates, and plan change frequency"},
    ],
    "procurement": [
        {"method": "User Interviews", "priority": "Primary", "count": "5–8",
         "rationale": "Deep-dive on procurement workflow, exception handling, and ERP pain points"},
        {"method": "Process Observation", "priority": "Secondary", "count": "1–2",
         "rationale": "Watch a procurement cycle in action — from requisition to payment"},
        {"method": "Data Pull (ERP/AP)", "priority": "Validation", "count": "90-day dataset",
         "rationale": "Invoice match rates, exception volumes, PO cycle times, contract compliance"},
    ],
    "repair": [
        {"method": "User Interviews", "priority": "Primary", "count": "5–8",
         "rationale": "Map repair workflow from service request to resolution — surface root causes of SLA failures"},
        {"method": "Field Observation", "priority": "Secondary", "count": "1–2",
         "rationale": "Accompany a field technician or depot team — observe parts handling and workflow reality"},
        {"method": "Data Pull (ITSM/ERP)", "priority": "Validation", "count": "90-day dataset",
         "rationale": "MTTR, SLA breach rates, parts availability rate, cost per repair trend"},
    ],
    "trade": [
        {"method": "User Interviews", "priority": "Primary", "count": "4–6",
         "rationale": "Understand trade compliance workflow, documentation pain, and broker dependency"},
        {"method": "Broker / Partner Interview", "priority": "Secondary", "count": "1–2",
         "rationale": "External perspective on where delays and errors originate"},
        {"method": "Data Pull (Trade System)", "priority": "Validation", "count": "6-month dataset",
         "rationale": "Clearance times, exception rates, duty paid vs. optimised"},
    ],
    "fraud": [
        {"method": "User Interviews", "priority": "Primary", "count": "4–6",
         "rationale": "Finance, AP, and audit teams — understand current detection process and confidence levels"},
        {"method": "Case Review", "priority": "Secondary", "count": "5–10 cases",
         "rationale": "Retrospective analysis of caught and missed fraud cases — quantify detection latency"},
        {"method": "Data Pull (AP/Finance)", "priority": "Validation", "count": "12-month dataset",
         "rationale": "Invoice exception rates, duplicate payments, claim anomalies, approval rate trends"},
    ],
}


# ------------------------------------------------------------------ #
# LLM Prompts
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
    Generates domain-aware, problem-specific research plans.

    Modes:
      quick_scan    — rule-based only (no LLM)
      standard      — LLM-enriched with Haiku (fast, ~15s)
      deep_research — LLM-enriched with Sonnet + extended thinking (~60s)
    """

    DOMAIN_LABELS: Dict[str, str] = {
        "planning":    "Planning & Forecasting",
        "procurement": "Procurement & Sourcing",
        "repair":      "Repair & MRO",
        "trade":       "Trade & Compliance",
        "fraud":       "Fraud & Risk",
    }

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
        Generates a domain-aware, problem-specific research plan from scored answers.

        Args:
            answers:          QuestionEngine.answers dict
            verdict:          VerdictResult from ScoringEngine
            idea_title:       User-provided idea title
            idea_description: User-provided idea description
            mode:             "quick_scan" | "standard" | "deep_research"
            cost_estimate:    Optional free-text cost/impact estimate
        Returns:
            Plan dict with interview_questions, data_signals, success_criteria, etc.
        """
        domain     = answers.get("q1", "")
        problem_id = answers.get("q2", "")
        q3         = answers.get("q3", "")
        q4         = answers.get("q4", "")
        q5         = answers.get("q5", {})

        problem_key = f"{domain}__{problem_id}"

        # ── Rule-based lookups ────────────────────────────────────────
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

        # ── Riskiest assumption and cheapest validation ───────────────
        riskiest, cheapest = self._infer_riskiest_assumption(domain, problem_id, q4, q5)

        # ── Participants ──────────────────────────────────────────────
        participants = self._build_participants(domain, q3)

        # ── Hypothesis ───────────────────────────────────────────────
        hypothesis = self._build_hypothesis(domain, problem_id, q3, q4, q5, answers)

        # ── Research methods ─────────────────────────────────────────
        research_methods = RESEARCH_METHODS.get(domain, RESEARCH_METHODS.get("procurement", []))

        # ── Timeline guidance ─────────────────────────────────────────
        timeline_guidance = self._get_timeline(mode, len(participants))

        domain_label  = self.DOMAIN_LABELS.get(domain, domain.capitalize())
        problem_label = Q2_LABELS.get(problem_id, problem_id)

        plan: Dict[str, Any] = {
            "source":               "rule_based",
            "domain":               domain,
            "domain_label":         domain_label,
            "problem_id":           problem_id,
            "problem_label":        problem_label,
            "idea_title":           idea_title,
            "_idea_description":    idea_description,
            "_answers":             answers,
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

        # ── LLM enrichment ────────────────────────────────────────────
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
        """Build primary + secondary participant list."""
        participants: List[Dict] = []

        # Primary stakeholder (from Q3)
        if q3:
            access_info = STAKEHOLDER_ACCESS.get(q3, {})
            participants.append({
                "role":   Q3_LABELS.get(q3, q3),
                "count":  "3–5",
                "access": access_info.get("access", "Medium"),
                "note":   access_info.get("note", ""),
                "known":  False,
            })

        # Secondary participants
        for sec in SECONDARY_PARTICIPANTS.get(domain, []):
            participants.append({**sec, "known": False})

        return participants

    # ------------------------------------------------------------------ #
    # Hypothesis builder
    # ------------------------------------------------------------------ #

    def _build_hypothesis(
        self,
        domain: str,
        problem_id: str,
        q3: str,
        q4: str,
        q5: Dict,
        answers: Dict,
    ) -> str:
        """Build a human-readable hypothesis from answers using domain templates."""
        template = DOMAIN_HYPOTHESES.get(domain, DOMAIN_HYPOTHESES.get("procurement", ""))
        if not template:
            return ""

        stakeholder = Q3_LABELS.get(q3, "supply chain stakeholders")
        problem     = Q2_LABELS.get(problem_id, "this problem")
        frequency   = FREQ_LABELS.get(q5.get("frequency", ""), "regularly")
        severity    = SEV_LABELS.get(q5.get("severity", ""), "creates friction")
        current_state = Q4_LABELS.get(q4, "existing processes")
        workaround  = WK_LABELS.get(q5.get("workaround_effort", ""), "manual workarounds")

        try:
            return template.format(
                stakeholder=stakeholder,
                problem=problem,
                frequency=frequency,
                severity=severity,
                current_state=current_state,
                workaround=workaround,
            )
        except KeyError:
            return f"{stakeholder} face {problem} — a clear opportunity for a targeted supply chain solution."

    # ------------------------------------------------------------------ #
    # Timeline guidance
    # ------------------------------------------------------------------ #

    def _get_timeline(self, mode: str, n_participants: int) -> str:
        """Return practical timeline guidance based on mode and scope."""
        if mode == "deep_research":
            return (
                "Allow 3–4 weeks: 1 week for scheduling and desk research, "
                "2 weeks for interviews and data pulls, 1 week for synthesis. "
                "Aim for at least 5 completed interviews before drawing conclusions."
            )
        elif n_participants >= 3:
            return (
                "Allow 2–3 weeks: schedule interviews in the first week, "
                "run data pulls in parallel, synthesise findings in week 3. "
                "Don't wait for all interviews to complete before pulling data."
            )
        else:
            return (
                "Allow 1–2 weeks for a focused validation sprint. "
                "Target 3–5 interviews minimum before updating your verdict."
            )

    # ------------------------------------------------------------------ #
    # LLM prompt builder
    # ------------------------------------------------------------------ #

    def _build_prompt(
        self,
        plan: Dict,
        verdict: Any,
        mode: str,
        cost_estimate: str,
    ) -> str:
        """Build the LLM prompt from plan and verdict data."""
        cost_estimate_line = (
            f"\nEstimated cost impact: {cost_estimate}" if cost_estimate else ""
        )

        # Resolve human-readable labels for all context fields
        answers  = plan.get("_answers", {})
        q5       = answers.get("q5", {})

        template = DEEP_RESEARCH_PROMPT if mode == "deep_research" else STANDARD_PROMPT
        return template.format(
            idea_title           = plan.get("idea_title", ""),
            idea_description     = plan.get("_idea_description", ""),
            domain               = plan.get("domain_label", plan.get("domain", "")),
            problem              = plan.get("problem_label", plan.get("problem_id", "")),
            stakeholder          = Q3_LABELS.get(answers.get("q3", ""), answers.get("q3", "")),
            current_state        = Q4_LABELS.get(answers.get("q4", ""), answers.get("q4", "")),
            frequency            = FREQ_LABELS.get(q5.get("frequency", ""), q5.get("frequency", "")),
            severity             = SEV_LABELS.get(q5.get("severity", ""), q5.get("severity", "")),
            workaround           = WK_LABELS.get(q5.get("workaround_effort", ""), q5.get("workaround_effort", "")),
            origin               = answers.get("origin", ""),
            score                = int(getattr(verdict, "final_score", 0)),
            cost_estimate_line   = cost_estimate_line,
            baseline_hypothesis  = plan.get("hypothesis", ""),
            riskiest_assumption  = plan.get("riskiest_assumption", ""),
        )

    # ------------------------------------------------------------------ #
    # LLM output merging
    # ------------------------------------------------------------------ #

    def _merge_llm_output(
        self,
        raw: str,
        plan: Dict,
        mode: str,
    ) -> Dict:
        """
        Parse and merge LLM JSON output into the rule-based plan.
        Falls back to the rule-based plan if parsing fails.
        """
        import json, re

        # Extract JSON block (handle markdown code fences)
        json_match = re.search(r"\{[\s\S]*\}", raw)
        if not json_match:
            return plan

        try:
            llm_data = json.loads(json_match.group())
        except json.JSONDecodeError:
            return plan

        # Merge — prefer LLM content where it's richer
        merged = dict(plan)
        merged["source"] = "llm_deep" if mode == "deep_research" else "llm_standard"

        for field in (
            "hypothesis", "riskiest_assumption", "cheapest_validation",
            "timeline_guidance", "participant_notes",
        ):
            val = llm_data.get(field, "").strip()
            if val:
                merged[field] = val

        for list_field in (
            "interview_questions", "data_signals", "success_criteria",
            "competing_hypotheses", "counter_arguments", "second_order_effects",
        ):
            val = llm_data.get(list_field)
            if isinstance(val, list) and val:
                merged[list_field] = val

        return merged

    # ------------------------------------------------------------------ #
    # Riskiest assumption inference
    # ------------------------------------------------------------------ #

    def _infer_riskiest_assumption(
        self, domain: str, problem_id: str, q4: str, q5: Dict
    ) -> tuple:
        """Return (riskiest_assumption, cheapest_validation) based on answers."""
        freq = q5.get("frequency", "")
        q4_manual = q4 in ("manual_spreadsheet", "not_handled")

        # Not-handled: biggest risk is it's truly ignored for a reason
        if q4 == "not_handled":
            return (
                "The problem is ignored because it is genuinely low priority — not because there is no solution.",
                "Ask 5 users in one day: 'Why hasn't this been solved before?' Listen for 'we've tried' vs. 'no one cares enough'."
            )

        # Rare frequency: risk is that it's not painful enough
        if freq == "rare":
            return (
                "The problem occurs rarely enough that users have adapted — and won't change behaviour even if a solution exists.",
                "Ask 3 users: 'When did this last happen?' If no one can give a specific recent example, the frequency assumption is wrong."
            )

        # Domain-specific riskiest assumptions
        riskiest_map = {
            "planning":    ("Planners would act on better forecast accuracy if they had it — rather than continuing to over-ride the system anyway.",
                           "Show a planner a mock 'higher accuracy' scenario and ask: 'What would you do differently?' Listen for hedging."),
            "procurement": ("The problem is in the tool or process — not in change resistance or incentive misalignment within procurement.",
                           "Interview one CPO or VP Procurement: 'What have you already tried to fix this?' Their answer reveals whether the barrier is technical or political."),
            "repair":      ("Parts availability or workflow is the real bottleneck — not technician skill gaps or customer expectation misalignment.",
                           "Pull 10 SLA-breached work orders and classify the root cause. If skills or customer issues dominate, the parts/workflow hypothesis is wrong."),
            "trade":       ("The compliance team has enough authority to change the process — it isn't locked to broker or regulatory constraints outside their control.",
                           "Ask your compliance lead: 'If you had a better tool tomorrow, what would stop you from changing how you work?' Listen for 'our broker decides that' responses."),
            "fraud":       ("Finance and legal will allow automated fraud flags to block payments — versus requiring human review of every alert.",
                           "Ask your CFO or General Counsel: 'Would you let an AI hold an invoice pending review?' Their answer immediately defines the product's scope."),
        }
        r, c = riskiest_map.get(domain, (
            "The problem is as frequent and severe as reported — not inflated in the moment of evaluation.",
            "Pull 2 weeks of data before conducting interviews. If the data contradicts the stated frequency, recalibrate."
        ))
        return r, c
