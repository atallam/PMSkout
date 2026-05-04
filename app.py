"""
Product Skout — Supply Chain Idea Evaluator
Streamlit app: adaptive questions → verdict score → research plan → idea card.
Run: streamlit run app.py
"""
import os
import sys
import json
from pathlib import Path
from dotenv import load_dotenv

import streamlit as st

# Load .env first so ANTHROPIC_API_KEY is available before any imports
load_dotenv()

# Resolve paths relative to this file so it runs from any directory
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from core.question_engine import QuestionEngine
from core.scoring_engine import ScoringEngine
from core.research_planner import ResearchPlanner
from core.idea_card import IdeaCardGenerator
from core.user_context_manager import (
    UserContextManager,
    ORG_TYPES, ORG_SIZES, REGIONS, DATA_SYSTEMS, METHOD_LABELS,
)
from core.constants import Q2_LABELS, Q3_LABELS, Q4_LABELS, FREQ_LABELS, SEV_LABELS, DOMAIN_LABELS
from llm.factory import LLMFactory
# ── Phase 4 & 5 modules ─────────────────────────────────────────────── #
from core.signal_ingester import SignalIngester
from core.ideas_like_this import IdeasLikeThis
from core.brm_tracker import (
    BRMTracker, OutcomeRecord, BenefitItem,
    BENEFIT_CATEGORIES, REALISATION_STATUS, MEASUREMENT_UNITS,
)
from core.dmaic_engine import DMAICEngine
from core.action_tracker import ActionTracker, ActionItem, ACTION_STATUSES
from core.integrations import (
    to_notion_markdown, to_jira_json_str, to_csv,
    build_webhook_payload, post_webhook,
    get_team_ideas, share_to_team, add_team_comment,
)
from core.team_manager import TeamManager
from core.domain_knowledge_engine import DomainKnowledgeEngine

# ------------------------------------------------------------------ #
# Page configuration
# ------------------------------------------------------------------ #

st.set_page_config(
    page_title="Product Skout · Supply Chain Idea Evaluator",
    page_icon="🔭",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# ------------------------------------------------------------------ #
# Custom CSS  (light-mode compatible)
# ------------------------------------------------------------------ #

st.markdown("""
<style>
  /* Global */
  .block-container { max-width: 760px; padding-top: 1.75rem; }
  h1, h2, h3 { font-weight: 700; color: #0f172a; }

  /* Score circle */
  .score-circle {
    width: 130px; height: 130px; border-radius: 50%;
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    margin: 0 auto 1rem auto; font-weight: 800;
  }
  .score-number { font-size: 40px; line-height: 1; }
  .score-label  { font-size: 12px; opacity: 0.70; margin-top: 2px; }

  /* Cards */
  .skout-card {
    background: #ffffff; border-radius: 10px;
    border: 1.5px solid #e2e8f0; padding: 14px 18px;
    margin-bottom: 10px;
  }
  .skout-card.highlight { border-color: #6366f1; background: #f5f3ff; }
  .skout-card.green  { border-color: #86efac; background: #f0fdf4; }
  .skout-card.yellow { border-color: #fbbf24; background: #fefce8; }
  .skout-card.orange { border-color: #fb923c; background: #fff7ed; }
  .skout-card.red    { border-color: #f87171; background: #fef2f2; }

  /* Dimension bar */
  .dim-bar-bg { background: #e2e8f0; border-radius: 4px; height: 8px; margin-top: 4px; }
  .dim-bar    { border-radius: 4px; height: 8px; }

  /* Flag chips */
  .flag-warning { background: #fff7ed; border-left: 3px solid #fb923c; color: #7c2d12;
                  padding: 8px 12px; border-radius: 0 8px 8px 0; margin-bottom: 8px; font-size: 13px; }
  .flag-info    { background: #eff6ff; border-left: 3px solid #60a5fa; color: #1e3a5f;
                  padding: 8px 12px; border-radius: 0 8px 8px 0; margin-bottom: 8px; font-size: 13px; }
  .flag-caution { background: #fefce8; border-left: 3px solid #facc15; color: #713f12;
                  padding: 8px 12px; border-radius: 0 8px 8px 0; margin-bottom: 8px; font-size: 13px; }

  /* Idea card */
  .idea-card-header {
    background: linear-gradient(135deg, #6366f1, #8b5cf6);
    border-radius: 10px 10px 0 0; padding: 18px 20px; color: white;
  }
  .idea-card-body  { border: 1.5px solid #6366f1; border-top: none;
                     border-radius: 0 0 10px 10px; padding: 16px 20px; }

  /* Step indicator */
  .step-text { font-size: 11px; color: #64748b; font-weight: 700;
               text-transform: uppercase; letter-spacing: 0.5px; }

  /* Hypothesis box */
  .hypothesis { background: #f5f3ff; border-left: 3px solid #6366f1; color: #1e1b4b;
                padding: 12px 14px; border-radius: 0 8px 8px 0;
                font-style: italic; font-size: 14px; line-height: 1.6; }

  /* Interview Q intent badge */
  .iq-intent { display: inline-block; font-size: 10px; font-weight: 700;
               padding: 1px 6px; border-radius: 20px; background: #ede9fe;
               color: #6d28d9; margin-left: 6px; }

  /* Competing hypothesis cards */
  .hyp-card { border: 1.5px solid #e2e8f0; border-radius: 10px;
              padding: 12px 14px; margin-bottom: 8px; background: #ffffff; }
  .hyp-card.primary { border-color: #6366f1; background: #f5f3ff; }
  .hyp-conf-high   { color: #15803d; font-weight: 700; font-size: 11px; }
  .hyp-conf-medium { color: #b45309; font-weight: 700; font-size: 11px; }
  .hyp-conf-low    { color: #dc2626; font-weight: 700; font-size: 11px; }

  /* Phase badge */
  .phase-badge {
    display: inline-block; font-size: 10px; font-weight: 700;
    padding: 2px 8px; border-radius: 20px;
  }
  .phase-0 { background: #f1f5f9; color: #475569; }
  .phase-1 { background: #ede9fe; color: #5b21b6; }
  .phase-2 { background: #dbeafe; color: #1d4ed8; }
  .phase-3 { background: #dcfce7; color: #15803d; }

  /* Similar idea alert */
  .similar-alert { background: #fefce8; border: 1px solid #fbbf24; color: #713f12;
                   border-radius: 8px; padding: 10px 14px; font-size: 13px;
                   margin-bottom: 12px; }

  /* Plan summary card */
  .plan-summary { background: #f5f3ff; border: 1.5px solid #a5b4fc;
                  border-radius: 10px; padding: 14px 18px; margin-bottom: 16px; color: #1e1b4b; }
  .plan-stat { display: inline-block; margin-right: 20px; font-size: 13px; }

  /* Data signal injected badge */
  .injected-badge { font-size: 10px; font-weight: 700; background: #dbeafe;
                    color: #1d4ed8; padding: 1px 6px; border-radius: 20px; margin-left: 4px; }
  .known-badge    { font-size: 10px; font-weight: 700; background: #dcfce7;
                    color: #15803d; padding: 1px 6px; border-radius: 20px; margin-left: 4px; }

  /* ── Phase 1 additions ── */

  /* Stage-Gate card */
  .gate-card {
    border-radius: 10px; padding: 12px 18px; margin-bottom: 10px;
    display: flex; align-items: center; gap: 12px;
  }
  .gate-dot {
    width: 14px; height: 14px; border-radius: 50%; flex-shrink: 0;
  }
  .gate-label { font-size: 15px; font-weight: 700; }
  .gate-sub   { font-size: 12px; opacity: 0.75; margin-top: 2px; }

  /* JTBD statement box */
  .jtbd-box {
    background: #f8fafc; border: 1.5px solid #cbd5e1;
    border-left: 4px solid #6366f1; border-radius: 0 8px 8px 0;
    padding: 12px 16px; margin-bottom: 10px; font-size: 14px;
    line-height: 1.65; color: #1e293b;
  }
  .jtbd-label {
    font-size: 10px; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.6px; color: #6366f1; margin-bottom: 6px;
  }

  /* 3 Horizons badge */
  .horizon-pill {
    display: inline-flex; align-items: center; gap: 6px;
    padding: 4px 12px; border-radius: 20px; font-size: 13px;
    font-weight: 700; margin-right: 8px;
  }
  .horizon-desc {
    font-size: 12px; color: #64748b; margin-top: 4px;
  }

  /* Benchmark row */
  .benchmark-row {
    font-size: 13px; color: #374151; padding: 10px 14px;
    background: #f1f5f9; border-radius: 8px; margin-bottom: 8px;
  }
  .benchmark-pct { font-size: 22px; font-weight: 800; color: #6366f1; }

  /* Cost estimate field */
  .cost-hint { font-size: 12px; color: #64748b; margin-top: -6px; margin-bottom: 8px; }

  /* Phase 2 — SCOR / WSJF / Opportunity Gap metrics strip */
  .metrics-strip {
    display: flex; gap: 10px; flex-wrap: wrap; margin: 12px 0;
  }
  .metric-card {
    flex: 1 1 120px; min-width: 110px;
    background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px;
    padding: 10px 12px;
  }
  .metric-card-label {
    font-size: 10px; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.5px; color: #64748b; margin-bottom: 4px;
  }
  .metric-card-value {
    font-size: 22px; font-weight: 800; line-height: 1;
  }
  .metric-card-sub {
    font-size: 11px; color: #94a3b8; margin-top: 3px;
  }
  .scor-pill {
    display: inline-flex; align-items: center; gap: 5px;
    background: #ede9fe; color: #5b21b6;
    padding: 3px 10px; border-radius: 12px;
    font-size: 12px; font-weight: 700;
  }
</style>
""", unsafe_allow_html=True)

# ------------------------------------------------------------------ #
# Session state initialisation
# ------------------------------------------------------------------ #

STEPS = [
    "onboarding", "idea_input", "origin", "q1", "q2", "q3", "q4", "q5",
    "verdict", "research_plan", "findings", "idea_card",
]

def init_state():
    """
    Initialise all Streamlit session state keys with safe defaults.
    Called once on page load and again when the user starts a new idea.
    Only sets keys that are not already present — never overwrites existing state.
    """
    defaults = {
        "step":              "idea_input",
        "idea_title":        "",
        "idea_description":  "",
        "engine":            None,
        "scorer":            None,
        "factory":           None,
        "ucm":               None,
        "verdict":           None,
        "research_plan":     None,
        "research_mode":     "standard",
        "findings":          ["", "", "", "", ""],
        "checked_criteria":  [],
        "proposed_direction": "",
        "open_questions":    ["", "", ""],
        "idea_card":         None,
        "idea_recorded":     False,
        "cost_estimate":     "",
        "domain_audit":      None,
        "domain_audit_ctx":  {},
        # ── Phase 4: ingestion + pattern matching + BRM + DMAIC ──
        "signal":            None,   # IdeaSignal from multi-source ingestion
        "dmaic_canvas":      None,   # DMAICCanvas from DMAIC engine
        # ── Phase 5: action tracker + integrations + team mode ──
        "actions_seeded":    False,  # True once action items auto-seeded from plan
        "team_mode":         False,  # Team Mode toggle
        "team_id":           "default",
        "webhook_url":       "",     # user-configured webhook endpoint
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_state()

# ------------------------------------------------------------------ #
# Engine lazy init
# ------------------------------------------------------------------ #

@st.cache_resource
def load_engines():
    """
    Load and cache the three stateless engines (shared across Streamlit reruns).
    Using @st.cache_resource ensures heavy YAML parsing happens only once per session.
    Returns (QuestionEngine, ScoringEngine, LLMFactory).
    """
    engine  = QuestionEngine("config/questions.yaml", "config/user_context.yaml")
    scorer  = ScoringEngine("config/scoring.yaml", "config/questions.yaml", "config/user_context.yaml")
    factory = LLMFactory("config/llm_config.yaml")
    return engine, scorer, factory

@st.cache_resource
def load_ucm():
    """
    Load and cache the UserContextManager (reads user_context.yaml + data/ideas.json).
    Ensures the data/ directory exists before loading.
    Cached so profile + history persist across Streamlit reruns within a session.
    """
    Path("data").mkdir(exist_ok=True)
    ucm = UserContextManager(
        context_path="config/user_context.yaml",
        ideas_path="data/ideas.json",
    )
    ucm.load()
    return ucm

try:
    _engine, _scorer, _factory = load_engines()
    if st.session_state.engine is None:
        st.session_state.engine  = _engine
        st.session_state.scorer  = _scorer
        st.session_state.factory = _factory
except Exception as e:
    st.error(f"Failed to load Product Skout config: {e}")
    st.stop()

try:
    _ucm = load_ucm()
    if st.session_state.ucm is None:
        st.session_state.ucm = _ucm
except Exception as e:
    st.warning(f"User context unavailable: {e}")

# ------------------------------------------------------------------ #
# Navigation helpers
# ------------------------------------------------------------------ #

def go(step: str):
    """Navigate to a named step and force a Streamlit rerun."""
    st.session_state.step = step
    st.rerun()

def prev_step(current: str):
    """Navigate to the step immediately before `current` in the STEPS list."""
    idx = STEPS.index(current)
    if idx > 0:
        go(STEPS[idx - 1])

def progress_bar(step: str):
    """
    Render a "Step X of Y" label + Streamlit progress bar for question steps.
    Only shown during the 6 question steps (origin → q5); hidden on other screens.
    """
    question_steps = ["origin", "q1", "q2", "q3", "q4", "q5"]
    if step in question_steps:
        idx   = question_steps.index(step) + 1
        total = len(question_steps)
        st.markdown(f'<p class="step-text">Step {idx} of {total}</p>', unsafe_allow_html=True)
        st.progress(idx / total)

def safe_radio(label, options_list, index=0, key=None):
    """
    Wrapper around st.radio that guarantees a valid (non-None) default.
    Prevents ValueError: None is not in list on first render.
    """
    idx = max(0, index) if index is not None else 0
    return st.radio(label, options_list, index=idx, key=key, label_visibility="collapsed")


# ------------------------------------------------------------------ #
# Phase 1 Helper Functions
# ------------------------------------------------------------------ #

# Label maps imported from core.constants — single source of truth.
# Q2_LABELS, Q3_LABELS, Q4_LABELS, FREQ_LABELS, SEV_LABELS are all available.

def get_jtbd_statement(engine) -> str:
    """Build a JTBD-style 'When X, Y faces Z' problem statement from current answers."""
    answers = engine.answers
    q2 = answers.get("q2", "")
    q3 = answers.get("q3", "")
    q4 = answers.get("q4", "")
    q5 = answers.get("q5", {}) or {}

    problem       = Q2_LABELS.get(q2, q2.replace("_", " ") if q2 else "this problem")
    stakeholder   = Q3_LABELS.get(q3, "supply chain teams")
    current_state = Q4_LABELS.get(q4, "existing processes")
    freq          = FREQ_LABELS.get(q5.get("frequency", ""), "regularly")
    severity      = SEV_LABELS.get(q5.get("severity", ""), "causing disruption")

    return (
        f"When **{current_state}**, **{stakeholder}** face **{problem}** "
        f"{freq}, {severity}. "
        f"A solution would let them focus on higher-value work instead of managing this gap."
    )


# H1 problem types where the domain signals core improvement work
_H1_PROBLEM_TYPES = {
    "forecast_accuracy", "sop_process", "po_cycle_time",
    "turnaround_time", "cost_per_repair", "invoice_reconciliation",
    "process_inefficiency",
}

def get_horizon(band: str, q4: str, q2: str) -> tuple:
    """
    Returns (horizon_code, horizon_label, bg_color, text_color, description).
    McKinsey 3 Horizons classification based on market gap + problem type.
    """
    if q4 == "not_handled":
        return (
            "H3", "Transformational Bet",
            "#ede9fe", "#5b21b6",
            "No existing solution exists — requires deep discovery before any investment.",
        )
    if q4 in ("siloed_tools", "competitor_exists"):
        return (
            "H2", "Adjacent Opportunity",
            "#dbeafe", "#1d4ed8",
            "Market exists but is underserved — differentiation and positioning are critical.",
        )
    if q2 in ("demand_sensing", "compliance_risk", "visibility_gaps", "counterfeit_parts"):
        return (
            "H2", "Adjacent Opportunity",
            "#dbeafe", "#1d4ed8",
            "Emerging problem space — early mover advantage if validated quickly.",
        )
    # Default: H1
    return (
        "H1", "Core Improvement",
        "#dcfce7", "#15803d",
        "Improving known workflows — lower risk; focus on ROI and clear differentiation.",
    )


def get_benchmark(ucm, domain: str, current_score: float):
    """
    Returns benchmark dict or None.
    Requires ≥2 historical scores to display.
    """
    if not ucm or ucm.get_phase() < 1:
        return None
    history = ucm.get_ideas_history()
    if not history:
        return None

    domain_scores = [i["score"] for i in history if i.get("domain") == domain and "score" in i]
    if len(domain_scores) >= 2:
        pct = int(sum(1 for s in domain_scores if s < current_score) / len(domain_scores) * 100)
        return {"percentile": pct, "count": len(domain_scores), "scope": domain.capitalize()}

    all_scores = [i["score"] for i in history if "score" in i]
    if len(all_scores) >= 2:
        pct = int(sum(1 for s in all_scores if s < current_score) / len(all_scores) * 100)
        return {"percentile": pct, "count": len(all_scores), "scope": "all domains"}

    return None


# Stage-Gate verdict mapping (Gate 1 framing)
_GATE_RECOMMENDATIONS = {
    "high_priority": ("🟢 Gate 1: Proceed to Scoping",          "#f0fdf4", "#15803d", "#86efac"),
    "promising":     ("🟡 Gate 1: Proceed with Validation",      "#fefce8", "#b45309", "#fbbf24"),
    "needs_clarity": ("🟠 Gate 1: Return to Discovery",          "#fff7ed", "#c2410c", "#fb923c"),
    "not_ready":     ("🔴 Gate 1: Shelve — Insufficient Signal", "#fef2f2", "#b91c1c", "#f87171"),
}

# ── Org-level Domain Audit configuration (predefined — not editable by team) ──
ORG_AUDIT_CONFIG = {
    "industry":                "electronics",
    "supply_chain_maturity":   "optimised",
    "disruption_environment":  "stable",
    "demand_pattern_primary":  "lumpy",          # Most constraining of the three patterns
    "demand_patterns_display": ["Trigger-driven", "Seasonal", "Lumpy"],
}


def _get_deep_dive_prompts(verdict, engine, audit=None):
    """
    Generate concise, data-driven deep-dive prompts across 6 strategic angles.
    2 prompts per angle, each 2-3 sentences and copy-paste ready.
    Uses actual verdict dimensions, scores, and audit findings — no hardcoded industry names.
    Returns an OrderedDict of angle_label -> list[str].
    """
    from collections import OrderedDict

    title  = st.session_state.get("idea_title", "this idea")
    domain = engine.answers.get("q1", "") if engine else ""
    score  = verdict.percent
    band   = verdict.band
    scor   = verdict.scor_category
    wsjf   = verdict.wsjf_score
    opp    = verdict.opportunity_gap

    idea_ref   = f'"{title}"' if title else "this idea"
    demand_str = " / ".join(ORG_AUDIT_CONFIG["demand_patterns_display"])

    band_label = {
        "high_priority": "high-priority",
        "promising":     "promising but unvalidated",
        "needs_clarity": "needs further clarity",
        "not_ready":     "not yet ready to progress",
    }.get(band, "evaluated")

    # ── Find weakest and strongest scoring dimensions ──
    _dim_labels = {
        "business_impact":   "business impact",
        "problem_clarity":   "problem clarity",
        "market_gap":        "market gap / competitive context",
        "stakeholder_reach": "stakeholder reach",
        "domain_fit":        "domain fit",
    }
    weakest_label, weakest_pct = "problem definition", 50
    strongest_label, strongest_pct = "domain fit", 50
    for dim, dim_score in verdict.dimension_scores.items():
        max_pts = verdict.dimension_max.get(dim, 30)
        pct = int((dim_score / max_pts) * 100) if max_pts else 0
        if pct < weakest_pct:
            weakest_pct, weakest_label = pct, _dim_labels.get(dim, dim)
        if pct > strongest_pct:
            strongest_pct, strongest_label = pct, _dim_labels.get(dim, dim)

    # ── Pull top audit signals (if available) ──
    top_challenge = ""
    top_kpi_warn  = ""
    if audit:
        if getattr(audit, "challenges", None):
            top_challenge = audit.challenges[0].name
        if getattr(audit, "kpi_warnings", None):
            top_kpi_warn = audit.kpi_warnings[0].kpi_name

    prompts = OrderedDict()

    # ── 1. Strategic ──────────────────────────────────────────────────
    prompts["🎯 Strategic"] = [
        f"I'm evaluating {idea_ref}, a supply chain initiative scored {score}/100 ({band_label}). "
        f"Its weakest dimension is {weakest_label} ({weakest_pct}%) and strongest is {strongest_label} ({strongest_pct}%). "
        f"Identify the 3 most critical strategic assumptions that must hold for this idea to succeed, "
        f"and design a 2-week validation sprint to test each one.",

        f"Position {idea_ref} using the McKinsey 3 Horizons model. "
        f"Its SCOR alignment is '{scor}', WSJF urgency {wsjf:.1f}/10, and Opportunity Gap {opp:.1f}/20. "
        f"Where does it sit today, what would move it from H1 to H2, and what single strategic decision "
        f"is the unlock?",
    ]

    # ── 2. Operational ───────────────────────────────────────────────
    prompts["⚙️ Operational"] = [
        f"Map the SCOR process changes required to implement {idea_ref} (aligned to: {scor}). "
        f"For each affected SCOR domain, specify: current-state pain → target-state change → "
        f"integration dependency → accountable owner. "
        f"Account for {demand_str} demand variability throughout.",

        f"Design a 90-day implementation roadmap for {idea_ref}. "
        f"Week 1–4: discovery and stakeholder alignment; Week 5–8: controlled pilot; Week 9–12: go-live and handoff. "
        f"Flag the top 3 dependencies that would break this timeline and what the contingency is for each.",
    ]

    # ── 3. Risk ──────────────────────────────────────────────────────
    if top_challenge:
        risk_p1 = (
            f"The domain audit flagged '{top_challenge}' as the top risk for {idea_ref}. "
            f"Conduct a 5-Whys root cause analysis on this failure mode. "
            f"For each root cause, specify a preventive control and an early warning KPI, "
            f"and rate residual risk as CRITICAL / HIGH / MEDIUM after controls are in place."
        )
    else:
        risk_p1 = (
            f"Conduct a FMEA-style risk assessment for {idea_ref} (score: {score}/100, {band_label}). "
            f"List the top 5 failure modes, score each on Severity × Occurrence × Detection (1–10), "
            f"and recommend one specific mitigation for the highest-RPN item."
        )

    prompts["⚠️ Risk"] = [
        risk_p1,
        f"Stress-test {idea_ref} against three demand scenarios: "
        f"(1) sudden spike in trigger-driven mode, "
        f"(2) seasonal trough following peak build-up, "
        f"(3) extended lumpy-demand gap with near-zero orders for 60 days. "
        f"For each, identify what breaks first and what buffer, flex capacity, or policy change prevents a failure.",
    ]

    # ── 4. Financial ─────────────────────────────────────────────────
    if top_kpi_warn:
        fin_p1 = (
            f"The domain audit flagged a KPI gap: '{top_kpi_warn}'. "
            f"Quantify the annual value of closing this gap through {idea_ref}. "
            f"Build a best / base / downside sensitivity table with the top 2 value drivers as axes."
        )
    else:
        fin_p1 = (
            f"Build a one-page business case for {idea_ref} (Opportunity Gap: {opp:.1f}/20, WSJF: {wsjf:.1f}/10). "
            f"Include: cost-of-delay per quarter if shelved, one-time investment buckets, "
            f"recurring cost savings or revenue uplift, and target payback period."
        )

    prompts["💰 Financial"] = [
        fin_p1,
        f"Rank {idea_ref} against 3 competing initiatives using WSJF (its current score: {wsjf:.1f}/10). "
        f"For each competitor initiative, estimate Cost of Delay and job size, then stack-rank all four. "
        f"What specifically would need to change — scope, timing, or value — "
        f"to move {idea_ref} to the top of the backlog?",
    ]

    # ── 5. Technical ─────────────────────────────────────────────────
    prompts["🔧 Technical"] = [
        f"Define the minimum data architecture to run {idea_ref} in production. "
        f"Specify: required source systems, data refresh cadence, quality SLAs, "
        f"and the single most likely data gap that would stall rollout. "
        f"If AI/ML is involved, include model drift monitoring and retraining cadence.",

        f"Evaluate build vs. buy vs. partner for {idea_ref} in a {domain or 'supply chain'} context. "
        f"Compare 3 existing market solutions on fit, integration complexity, and TCO. "
        f"Recommend a decision with a 12-month delivery plan and name the top 2 technical risks.",
    ]

    # ── 6. Stakeholder ───────────────────────────────────────────────
    prompts["👥 Stakeholder"] = [
        f"Map the power/interest grid for {idea_ref}. "
        f"For each quadrant (high power/high interest through to low/low), write a one-paragraph "
        f"engagement strategy and identify the single most likely source of resistance with a pre-emption tactic.",

        f"Write a 3-minute verbal pitch for {idea_ref} (score: {score}/100) targeting a VP of Supply Chain. "
        f"Structure: hook (cost of the problem) → solution → 3 metrics that prove value → specific ask. "
        f"End with the one objection they will definitely raise and your prepared response.",
    ]

    return prompts


# ------------------------------------------------------------------ #
# VERDICT SCREEN HELPERS
# ------------------------------------------------------------------ #

def _build_decision(verdict) -> dict:
    """
    Map verdict band to a GO / REFINE / STOP decision with a rationale.
    Returns dict: label, emoji, color, bg, rationale.
    """
    dim_labels = {
        "business_impact":   "business impact",
        "problem_clarity":   "problem clarity",
        "market_gap":        "market gap",
        "stakeholder_reach": "stakeholder reach",
        "domain_fit":        "domain fit",
    }
    # Find weakest and strongest dimension
    weakest_label, weakest_pct  = "problem definition", 50
    strongest_label, strongest_pct = "domain fit", 50
    for dim, score in verdict.dimension_scores.items():
        max_pts = verdict.dimension_max.get(dim, 30)
        pct = int((score / max_pts) * 100) if max_pts else 0
        if pct < weakest_pct:
            weakest_pct, weakest_label = pct, dim_labels.get(dim, dim)
        if pct > strongest_pct:
            strongest_pct, strongest_label = pct, dim_labels.get(dim, dim)

    band = verdict.band
    score = verdict.percent

    if band == "high_priority":
        return {
            "label": "GO",
            "emoji": "🟢",
            "color": "#15803d",
            "bg":    "#f0fdf4",
            "border": "#86efac",
            "rationale": (
                f"This idea scored **{score}/100** with strong {strongest_label} ({strongest_pct}%). "
                f"Signal is sufficient to move to scoping — prioritise strengthening {weakest_label} "
                f"({weakest_pct}%) as you define the build."
            ),
        }
    elif band == "promising":
        return {
            "label": "REFINE",
            "emoji": "🟡",
            "color": "#b45309",
            "bg":    "#fefce8",
            "border": "#fbbf24",
            "rationale": (
                f"Scored **{score}/100** — promising but not ready to commit. "
                f"{strongest_label.capitalize()} ({strongest_pct}%) is your strongest asset, "
                f"but {weakest_label} ({weakest_pct}%) needs validation before the idea earns a scoping slot."
            ),
        }
    elif band == "needs_clarity":
        return {
            "label": "REFINE",
            "emoji": "🟠",
            "color": "#c2410c",
            "bg":    "#fff7ed",
            "border": "#fb923c",
            "rationale": (
                f"Scored **{score}/100** — key gaps are blocking progress. "
                f"{weakest_label.capitalize()} ({weakest_pct}%) and {strongest_label} ({strongest_pct}%) "
                f"show a wide spread; close the gap on the weaker dimension before re-evaluating."
            ),
        }
    else:  # not_ready
        return {
            "label": "STOP",
            "emoji": "🔴",
            "color": "#b91c1c",
            "bg":    "#fef2f2",
            "border": "#fca5a5",
            "rationale": (
                f"Scored **{score}/100** — insufficient signal to proceed. "
                f"Revisit the problem framing; {weakest_label} ({weakest_pct}%) suggests the hypothesis "
                f"needs rethinking before any investment."
            ),
        }


def _build_stress_test(verdict, engine, audit=None) -> list:
    """
    Return a list of dicts, one per weak dimension (below 65 pct).
    Each dict: dimension, pct, question, ai_prompt.
    Max 4 items; always includes at least 2 even if dimensions are strong.
    """
    dim_labels = {
        "business_impact":   "Business Impact",
        "problem_clarity":   "Problem Clarity",
        "market_gap":        "Market Gap",
        "stakeholder_reach": "Stakeholder Reach",
        "domain_fit":        "Domain Fit",
    }
    dim_questions = {
        "business_impact": (
            "What is the measurable cost of NOT solving this? "
            "Can you put a number on it — dollars saved, hours recovered, error rate reduced?"
        ),
        "problem_clarity": (
            "Who specifically is experiencing this problem today, and what is their current workaround? "
            "Have you spoken with at least 3 people who live this pain?"
        ),
        "market_gap": (
            "What existing tools or processes already address this? "
            "What would make your solution 10× better — not just incrementally better?"
        ),
        "stakeholder_reach": (
            "Who are the 3 decision-makers who must approve or adopt this? "
            "What do they currently believe about this problem?"
        ),
        "domain_fit": (
            "How closely does this align to your organisation's current SC capability and roadmap? "
            "What adoption risk exists if you move forward without a domain champion?"
        ),
    }

    title  = st.session_state.get("idea_title", "this idea")
    domain = engine.answers.get("q1", "") if engine else "supply chain"
    score  = verdict.percent
    band   = verdict.band
    scor   = verdict.scor_category
    idea_ref = f'"{title}"' if title else "this idea"
    demand_str = " / ".join(ORG_AUDIT_CONFIG["demand_patterns_display"])

    # Pull audit signals
    top_challenge = ""
    if audit and getattr(audit, "challenges", None):
        top_challenge = audit.challenges[0].name

    dim_prompts = {
        "business_impact": (
            f"I'm evaluating {idea_ref} in the {domain} domain (score: {score}/100, SCOR: {scor}). "
            f"The business impact dimension scored low. "
            f"Help me build a one-page cost-of-delay model: "
            f"(1) quantify the annual cost if this is NOT solved, "
            f"(2) estimate the value captured in Year 1 if it IS solved, "
            f"(3) identify the top 2 assumptions that would invalidate the business case. "
            f"Use {demand_str} demand patterns as the operating context."
        ),
        "problem_clarity": (
            f"I'm trying to validate the problem statement for {idea_ref} (score: {score}/100). "
            f"Problem clarity is weak. "
            f"Write me 5 discovery interview questions that would confirm or refute whether this is a real, "
            f"urgent problem worth solving — not leading questions, genuine probes. "
            f"Then suggest 3 observable signals (data or behaviours) that would constitute strong evidence."
        ),
        "market_gap": (
            f"For {idea_ref} in the {domain or 'supply chain'} domain (SCOR: {scor}), "
            f"the market gap dimension is weak. "
            f"Identify the top 3 existing solutions (vendors, internal tools, manual processes) that already "
            f"address this space. For each, describe what they do well and where they fall short. "
            f"Then define what a 10× improvement would look like and whether {idea_ref} could deliver it."
        ),
        "stakeholder_reach": (
            f"For {idea_ref} (score: {score}/100), stakeholder reach scored low. "
            f"Map a power/interest grid for this initiative: "
            f"name the roles most affected, their likely stance (champion / neutral / resistant), "
            f"and the single most important thing each group needs to believe before they'll support it. "
            f"Suggest one concrete action to build buy-in with the most influential sceptic."
        ),
        "domain_fit": (
            f"{idea_ref} scored low on domain fit in a {domain or 'supply chain'} context. "
            + (f"The domain audit flagged '{top_challenge}' as a concern. " if top_challenge else "")
            + f"Identify the 3 most important supply chain capabilities an organisation needs to successfully "
            f"adopt this idea. For each capability, suggest a diagnostic question to test whether the "
            f"organisation already has it — and what the gap-closure plan would be if they don't."
        ),
    }

    # Score each dimension
    scored = []
    for dim, score_val in verdict.dimension_scores.items():
        max_pts = verdict.dimension_max.get(dim, 30)
        pct = int((score_val / max_pts) * 100) if max_pts else 0
        scored.append((pct, dim))
    scored.sort()  # weakest first

    items = []
    for pct, dim in scored[:4]:
        if dim not in dim_labels:
            continue
        items.append({
            "dimension": dim_labels[dim],
            "pct":       pct,
            "question":  dim_questions.get(dim, "What assumption is most at risk here?"),
            "ai_prompt": dim_prompts.get(dim, ""),
        })
        if len(items) >= 4:
            break

    # Ensure at least 2 items
    if len(items) < 2:
        for pct, dim in scored:
            if dim in dim_labels and not any(i["dimension"] == dim_labels[dim] for i in items):
                items.append({
                    "dimension": dim_labels[dim],
                    "pct":       pct,
                    "question":  dim_questions.get(dim, "What assumption is most at risk here?"),
                    "ai_prompt": dim_prompts.get(dim, ""),
                })
            if len(items) >= 2:
                break

    return items


def _build_action_plan(verdict, engine, audit=None) -> list:
    """
    Return a list of action step dicts: {step, owner, why, tag}.
    Steps are prioritised by band and weak dimensions.
    """
    band   = verdict.band
    domain = engine.answers.get("q1", "") if engine else ""
    q2     = engine.answers.get("q2", "") if engine else ""

    dim_labels = {
        "business_impact":   "business impact",
        "problem_clarity":   "problem clarity",
        "market_gap":        "market gap",
        "stakeholder_reach": "stakeholder reach",
        "domain_fit":        "domain fit",
    }
    scored = sorted(
        [(int((s / verdict.dimension_max.get(d, 30)) * 100) if verdict.dimension_max.get(d, 30) else 0, d)
         for d, s in verdict.dimension_scores.items()]
    )
    weakest_dim   = dim_labels.get(scored[0][1], "the weakest area") if scored else "problem definition"
    second_weak   = dim_labels.get(scored[1][1], "stakeholder alignment") if len(scored) > 1 else "stakeholder alignment"
    top_challenge = ""
    if audit and getattr(audit, "challenges", None):
        top_challenge = audit.challenges[0].name

    domain_str = domain.replace("_", " ").title() if domain else "supply chain"
    q2_str     = q2.replace("__", " — ").replace("_", " ").title() if q2 else "the identified problem"

    if band == "high_priority":
        steps = [
            {"step": f"Define scope and success metrics for '{q2_str}'",
             "owner": "PM",
             "why":   "Lock in the north-star KPI before scoping begins so progress can be measured objectively.",
             "tag":   "NOW"},
            {"step": f"Schedule discovery sessions with 3 frontline {domain_str} stakeholders",
             "owner": "PM + Ops Lead",
             "why":   "Validate the problem is felt at the operational level before design starts.",
             "tag":   "NOW"},
            {"step": f"Strengthen {weakest_dim} — build a cost-of-delay estimate",
             "owner": "Finance + PM",
             "why":   "This is the weakest scoring dimension; a quantified business case will ease approval.",
             "tag":   "NEXT"},
            {"step": "Identify the data sources and system integrations required",
             "owner": "Data Lead",
             "why":   "Data readiness is a common blocker; surface gaps now before build commitment.",
             "tag":   "NEXT"},
            {"step": "Present scoping brief to leadership for Gate 1 approval",
             "owner": "PM + Stakeholder",
             "why":   "Gate 1 approval converts the idea into a funded initiative.",
             "tag":   "LATER"},
        ]
    elif band in ("promising", "needs_clarity"):
        steps = [
            {"step": f"Run 3–5 structured discovery interviews focused on {weakest_dim}",
             "owner": "PM",
             "why":   f"This dimension scored lowest — field evidence will either confirm or kill the hypothesis quickly.",
             "tag":   "NOW"},
            {"step": f"Clarify {second_weak} — map who is affected and quantify the pain",
             "owner": "PM + Ops Lead",
             "why":   "Two weak dimensions means the case isn't compelling yet; address both before re-scoring.",
             "tag":   "NOW"},
            {"step": f"Audit existing solutions: what already addresses '{q2_str}'?",
             "owner": "PM",
             "why":   "Market gap needs evidence of differentiation, not just assumption.",
             "tag":   "NEXT"},
            ({"step": f"Address domain audit risk: '{top_challenge}'",
              "owner": "Ops Lead",
              "why":   "The audit flagged this as a material risk — it must be mitigated or accepted explicitly.",
              "tag":   "NEXT"} if top_challenge else
             {"step": "Document assumptions and design a 2-week spike to test the riskiest one",
              "owner": "PM",
              "why":   "Assumption-driven spikes are the fastest way to build or kill confidence.",
              "tag":   "NEXT"}),
            {"step": "Re-score after incorporating discovery findings",
             "owner": "PM",
             "why":   "A re-score after validation avoids anchoring on the original assessment.",
             "tag":   "LATER"},
        ]
    else:  # not_ready
        steps = [
            {"step": "Write a crisp one-paragraph problem statement and test it with 2 colleagues",
             "owner": "PM",
             "why":   "Low scores across dimensions suggest the problem framing itself needs sharpening.",
             "tag":   "NOW"},
            {"step": f"Validate whether '{q2_str}' is the right problem to solve in {domain_str}",
             "owner": "PM + Ops Lead",
             "why":   "Before investing further, confirm the problem is real and worth solving.",
             "tag":   "NOW"},
            {"step": "Shelve this idea and set a 4-week review date",
             "owner": "PM",
             "why":   "A time-boxed pause prevents effort waste while keeping the option open.",
             "tag":   "NOW"},
            {"step": "Identify one adjacent problem in the same domain that scores higher",
             "owner": "PM",
             "why":   "Pivoting to a stronger variant is often faster than fixing a weak hypothesis.",
             "tag":   "NEXT"},
        ]

    return steps


# ------------------------------------------------------------------ #
# SCREEN: Onboarding Wizard
# ------------------------------------------------------------------ #

def screen_onboarding():
    """
    SCREEN: Onboarding Wizard
    Collects user profile, organisation details, primary domains, connected data
    systems, and research preferences. Calls ucm.apply_onboarding() on submit.
    Skip button available for users who want to start immediately.
    """
    st.markdown("# 🔭 Welcome to Product Skout")
    st.markdown(
        "Product Skout learns your context over time — your organisation, domains, and preferred "
        "research methods — to personalise every evaluation. This takes about 60 seconds."
    )
    st.divider()

    with st.form("onboarding_form"):
        st.markdown("### 👤 About You")
        col1, col2 = st.columns(2)
        with col1:
            name = st.text_input("Your name", placeholder="e.g. Avinash")
        with col2:
            role = st.text_input("Your role", placeholder="e.g. Senior Product Manager")

        st.markdown("### 🏢 Your Organisation")
        col3, col4 = st.columns(2)
        with col3:
            org_name = st.text_input("Organisation name", placeholder="e.g. Acme Supply Co.")
            org_type = st.selectbox("Organisation type", ORG_TYPES)
        with col4:
            org_size = st.selectbox("Organisation size", ORG_SIZES)
            regions  = st.multiselect("Regions you operate in", REGIONS)

        st.markdown("### 🎯 Your Focus Areas")
        domain_options = list(DOMAIN_LABELS.items())
        domain_labels  = [v for _, v in domain_options]
        domain_ids     = [k for k, _ in domain_options]
        primary_labels = st.multiselect(
            "Primary supply chain domains (select 1–3)",
            domain_labels, max_selections=3,
        )
        primary_domains = [domain_ids[domain_labels.index(l)] for l in primary_labels]

        st.markdown("### 🗄️ Connected Data Systems")
        data_sources = st.multiselect(
            "Which systems does your team use?",
            DATA_SYSTEMS,
            help="These will appear as pre-populated data signals in your research plans.",
        )

        st.markdown("### ⚙️ Research Preferences")
        col5, col6 = st.columns(2)
        with col5:
            interview_count = st.slider("Default interview target", 3, 15, 5)
        with col6:
            deep_think_threshold = st.slider(
                "Deep Research threshold", 60, 100, 80, step=5,
                help="Ideas scoring above this unlock Deep Research automatically.",
            )

        st.markdown("### 👥 Team Setup")
        st.caption(
            "Skout surfaces ideas from teammates who are working on adjacent problems. "
            "Set your role and a shared Team ID so your pool is correctly scoped."
        )
        col7, col8 = st.columns(2)
        with col7:
            role_type = st.selectbox(
                "Your role in Skout",
                options=["pm", "team_lead", "director"],
                format_func=lambda x: {
                    "pm":        "📋 Product Manager — evaluate ideas & see adjacencies",
                    "team_lead": "🔗 Team Lead — flag ideas for collaboration",
                    "director":  "📊 Director — portfolio read-only view",
                }[x],
                help="Controls what you see in the sidebar.",
            )
        with col8:
            team_id = st.text_input(
                "Team ID",
                value="default",
                placeholder="e.g. sc-emea or procurement-na",
                help="Ideas shared within the same Team ID appear in your team pool. "
                     "Use a short identifier agreed with your team.",
            ).strip() or "default"

        st.divider()
        submitted = st.form_submit_button(
            "Save Profile & Start Evaluating →", type="primary", use_container_width=True
        )

    if submitted:
        if not name.strip() or not role.strip():
            st.error("Please enter your name and role to continue.")
        else:
            ucm = st.session_state.get("ucm")
            if ucm:
                ucm.apply_onboarding({
                    "name": name.strip(), "role": role.strip(),
                    "role_type": role_type, "team_id": team_id,
                    "org_name": org_name.strip(), "org_type": org_type,
                    "org_size": org_size, "regions": regions,
                    "primary_domains": primary_domains,
                    "data_sources": data_sources,
                    "interview_count": interview_count,
                    "deep_think_threshold": deep_think_threshold,
                })
                # Sync team_id into session state for immediate use
                st.session_state["team_id"] = team_id
            st.success(f"Profile saved! Welcome, {name}.")
            go("idea_input")

    st.markdown("---")
    if st.button("Skip for now →"):
        ucm = st.session_state.get("ucm")
        if ucm:
            ucm.apply_onboarding({"name": "User", "role": "PM",
                                   "role_type": "pm", "team_id": "default"})
        go("idea_input")

# ------------------------------------------------------------------ #
# SCREEN: Idea Input
# ------------------------------------------------------------------ #

def screen_idea_input():
    """
    SCREEN: Idea Input
    Home screen where the PM enters an idea title and 1–2 sentence description.
    Redirects unonboarded users to the onboarding wizard first.
    Shows phase badge and launches the question flow on submit.
    """
    ucm = st.session_state.get("ucm")
    if ucm and not ucm.is_onboarded():
        go("onboarding")
        return

    st.markdown("# 🔭 Product Skout")
    st.markdown(
        "**Supply Chain Idea Evaluator** — 5 adaptive questions, a verdict score, "
        "and a research plan. Know whether your idea is worth pursuing before writing a line of spec."
    )

    if ucm:
        phase = ucm.get_phase()
        phase_colors = {0: "phase-0", 1: "phase-1", 2: "phase-2", 3: "phase-3"}
        st.markdown(
            f'<span class="phase-badge {phase_colors[phase]}">{ucm.phase_label()}</span>',
            unsafe_allow_html=True,
        )

    st.divider()

    st.session_state.idea_title = st.text_input(
        "Give your idea a name",
        value=st.session_state.idea_title,
        placeholder="e.g. Automated Invoice Reconciliation for Procurement",
    )
    st.session_state.idea_description = st.text_area(
        "Describe it in 1–2 sentences",
        value=st.session_state.idea_description,
        placeholder="e.g. A tool that automatically matches supplier invoices to POs and routes exceptions — replacing a manual process that takes 12+ hrs/week.",
        height=85,
    )

    # ── Phase 4: Multi-source Signal Ingestion ──────────────────────
    with st.expander("📡 Import signal from Slack, Jira, or ERP export", expanded=False):
        st.caption(
            "Paste messages, Jira JSON, or upload a CSV export. "
            "Skout will auto-detect the source and pre-fill the idea fields above."
        )
        source_tab, upload_tab = st.tabs(["📋 Paste text / JSON", "📂 Upload CSV"])

        with source_tab:
            pasted = st.text_area(
                "Paste Slack messages, Jira JSON, or any text signal here",
                height=120,
                placeholder='{ "summary": "Invoice reconciliation takes 3 days...", "description": "..." }',
                key="signal_paste",
            )
            if st.button("🔍 Parse Signal", key="parse_signal"):
                if pasted.strip():
                    sig = SignalIngester.auto_detect(pasted.strip())
                    st.session_state.signal = sig
                    if not st.session_state.idea_title.strip():
                        st.session_state.idea_title = sig.suggested_title
                    if not st.session_state.idea_description.strip():
                        st.session_state.idea_description = sig.suggested_description
                    st.rerun()

        with upload_tab:
            uploaded = st.file_uploader("Upload ERP/system CSV export", type=["csv", "txt"], key="signal_csv")
            if uploaded and st.button("🔍 Parse CSV", key="parse_csv"):
                sig = SignalIngester.from_csv(uploaded.read(), filename=uploaded.name)
                st.session_state.signal = sig
                if not st.session_state.idea_title.strip():
                    st.session_state.idea_title = sig.suggested_title
                if not st.session_state.idea_description.strip():
                    st.session_state.idea_description = sig.suggested_description
                st.rerun()

        sig = st.session_state.get("signal")
        if sig:
            conf_color = {"high": "🟢", "medium": "🟡", "low": "🔴"}.get(sig.confidence, "⚪")
            st.markdown(
                f'<div style="background:#f0fdf4;border:1px solid #86efac;border-radius:8px;'
                f'padding:10px 14px;font-size:12px;color:#14532d;margin-top:8px">'
                f'<strong>{conf_color} Signal parsed</strong> · Source: <code>{sig.source_type}</code> · '
                f'Domain hint: <strong>{sig.detected_domain}</strong><br/>'
                + ("".join(f"<div>• {s[:120]}</div>" for s in sig.signals[:4]))
                + (f"<div style='margin-top:4px;color:#64748b'>{len(sig.warnings)} warning(s)</div>" if sig.warnings else "")
                + "</div>",
                unsafe_allow_html=True,
            )
            if sig.metrics:
                st.caption("📊 Detected metrics: " + " · ".join(
                    f"{m['name']}: {m['value']} {m['unit']}" for m in sig.metrics[:4]
                ))

    col1, col2, col3 = st.columns([3, 1, 1])
    with col2:
        if st.button("Start Evaluation →", type="primary", use_container_width=True):
            if not st.session_state.idea_title.strip():
                st.error("Give your idea a name to get started.")
            else:
                st.session_state.engine.reset()
                st.session_state.idea_recorded = False
                go("origin")
    with col3:
        _ucm_btn = st.session_state.get("ucm")
        _has_hist = bool(_ucm_btn and _ucm_btn.get_ideas_history())
        if st.button("📂 All Ideas", use_container_width=True, disabled=not _has_hist):
            go("history")

    # ── Previous Ideas ────────────────────────────────────────────────
    _ucm_hi = st.session_state.get("ucm")
    if _ucm_hi:
        _all_ideas = _ucm_hi.get_ideas_history()
        if _all_ideas:
            st.divider()
            st.markdown("### 📂 Previous Ideas")
            st.caption(f"{len(_all_ideas)} idea(s) evaluated · click **Load** to restore any verdict")

            _band_meta = {
                "high_priority": ("🟢", "#f0fdf4", "#15803d", "#86efac", "GO"),
                "promising":     ("🟡", "#fefce8", "#b45309", "#fbbf24", "REFINE"),
                "needs_clarity": ("🟠", "#fff7ed", "#c2410c", "#fb923c", "REFINE"),
                "not_ready":     ("🔴", "#fef2f2", "#b91c1c", "#fca5a5", "STOP"),
            }

            for _idx, _idea in enumerate(_all_ideas):
                _band   = _idea.get("verdict", {}).get("band", "")
                _emoji, _bg, _fg, _border, _dec = _band_meta.get(
                    _band, ("⚪", "#f8fafc", "#374151", "#e2e8f0", "—")
                )
                _score  = int(_idea.get("score", 0))
                _title  = _idea.get("title", "Untitled")
                _domain = _idea.get("domain", "").replace("_", " ").title()
                _date   = _idea.get("date", "")
                _outcome = _idea.get("outcome", "")

                _ca, _cb = st.columns([5, 1])
                with _ca:
                    st.markdown(
                        f'<div style="background:{_bg};border:1px solid {_border};border-radius:8px;'
                        f'padding:10px 14px;margin-bottom:4px">'
                        f'<div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">'
                        f'<span style="font-size:16px">{_emoji}</span>'
                        f'<span style="font-size:14px;font-weight:600;color:#0f172a">{_title}</span>'
                        f'<span style="font-size:12px;font-weight:700;color:{_fg}">{_score}/100</span>'
                        f'<span style="font-size:11px;color:#64748b">{_domain}</span>'
                        f'<span style="font-size:11px;color:#94a3b8">{_date}</span>'
                        + (f'<span style="font-size:11px;background:#e0f2fe;color:#0369a1;'
                           f'padding:1px 6px;border-radius:3px">{_outcome}</span>' if _outcome else "")
                        + f'</div></div>',
                        unsafe_allow_html=True,
                    )
                with _cb:
                    if _idea.get("verdict"):
                        if st.button("Load ↗", key=f"hi_load_{_idx}", use_container_width=True):
                            from core.scoring_engine import VerdictResult as _VR2
                            st.session_state.idea_title       = _idea.get("title", "")
                            st.session_state.idea_description = ""
                            st.session_state.verdict          = _VR2.from_dict(_idea["verdict"])
                            st.session_state.idea_recorded    = True
                            st.session_state.domain_audit     = None
                            st.session_state.research_plan    = None
                            st.session_state.dmaic_canvas     = None
                            st.session_state.idea_findings    = {}
                            if _idea.get("answers"):
                                st.session_state.engine.answers = dict(_idea["answers"])
                            go("verdict")
                    else:
                        st.caption("—")

# ------------------------------------------------------------------ #
# SCREEN: Origin Pre-Question
# ------------------------------------------------------------------ #

def screen_origin():
    """
    SCREEN: Origin Pre-Question (Q0)
    Asks where the idea came from (user reports, PM hypothesis, usage data, etc.).
    The selected option sets an origin_multiplier that scales the final score.
    High-external-validation origins boost the score; internal hypotheses reduce it.
    """
    progress_bar("origin")
    st.markdown("### Before we evaluate — where did this idea come from?")
    st.caption("This shapes how much weight we give the signal behind your idea.")

    engine  = st.session_state.engine
    pq      = engine.get_pre_question()
    options = pq["options"]
    labels  = [f"{o['icon']}  {o['label']}" for o in options]

    current = engine.answers.get("origin")
    index   = 0
    if current:
        ids = [o["id"] for o in options]
        if current in ids:
            index = ids.index(current)

    chosen_label = safe_radio("Source", labels, index=index)
    chosen       = options[labels.index(chosen_label)]

    mult = chosen.get("multiplier", 1.0)
    if mult > 1.0:
        st.success(f"✓ User-validated signal — score multiplier **×{mult}** applied")
    elif mult == 1.0:
        st.info("Baseline signal — score unmodified. Consider validating with users.")
    else:
        st.warning(f"Low external validation — multiplier **×{mult}** reduces final score")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("← Back", use_container_width=True):
            prev_step("origin")
    with col2:
        if st.button("Next →", type="primary", use_container_width=True):
            engine.record_answer("origin", chosen["id"])
            go("q1")

# ------------------------------------------------------------------ #
# SCREEN: Q1 — Domain
# ------------------------------------------------------------------ #

def screen_q1():
    """
    SCREEN: Q1 — Supply chain domain selection.
    Filters out WIP domains. Pre-selects the user's most-evaluated domain at Phase 1+.
    Shows a 'similar ideas' notice if the user has prior ideas in the same domain.
    Answer drives Q2's adaptive branching (domain-specific problems).
    """
    progress_bar("q1")
    engine  = st.session_state.engine
    ucm     = st.session_state.get("ucm")
    q       = engine.get_question("q1")

    st.markdown(f"### Q1. {q['text']}")
    st.caption(q.get("help", ""))

    options   = engine.get_options("q1")   # hidden options already filtered
    current   = engine.answers.get("q1")
    suggested = ucm.get_suggested_domain() if ucm else None

    labels = [f"{o.get('icon','')}  {o['label']}" for o in options]

    index = 0
    if current:
        ids = [o["id"] for o in options]
        if current in ids:
            index = ids.index(current)
    elif suggested:
        ids = [o["id"] for o in options]
        if suggested in ids:
            index = ids.index(suggested)

    if suggested and not current:
        st.info(f"💡 Pre-filled from your most-evaluated domain: **{DOMAIN_LABELS.get(suggested, suggested)}**. Change freely.")

    chosen_label = safe_radio("Domain", labels, index=index)
    chosen       = options[labels.index(chosen_label)]

    if chosen.get("description"):
        st.caption(f"*{chosen['description']}*")

    # Similar ideas notice (Phase 1+ only, only when there are actual prior ideas)
    if ucm and ucm.get_phase() >= 1:
        similar = ucm.find_similar_ideas(chosen["id"], "")
        if similar:
            st.markdown(
                f'<div class="similar-alert">📂 You\'ve evaluated <strong>{len(similar)} previous '
                f'idea(s)</strong> in this domain — check the sidebar for details.</div>',
                unsafe_allow_html=True,
            )

    col1, col2 = st.columns(2)
    with col1:
        if st.button("← Back", use_container_width=True):
            prev_step("q1")
    with col2:
        if st.button("Next →", type="primary", use_container_width=True):
            engine.record_answer("q1", chosen["id"])
            go("q2")

# ------------------------------------------------------------------ #
# SCREEN: Q2 — Problem (adaptive on Q1 domain)
# ------------------------------------------------------------------ #

def screen_q2():
    """
    SCREEN: Q2 — Problem type (adaptive on Q1 domain answer).
    Shows domain-filtered problem options. Provides a free-text field when
    'other' is selected. Problem answer drives problem-specific interview questions,
    data signals, and success criteria in the Research Plan.
    """
    progress_bar("q2")
    engine       = st.session_state.engine
    q            = engine.get_question("q2")
    domain_label = engine.get_label("q1", engine.answers.get("q1", ""))

    st.markdown(f"### Q2. {q['text']}")
    st.caption(f"Domain: **{domain_label}** — options tailored to this domain")

    options = engine.get_options("q2")
    current = engine.answers.get("q2")
    labels  = [f"{o.get('icon','')}  {o['label']}" for o in options]

    index = 0
    if current:
        ids = [o["id"] for o in options]
        if current in ids:
            index = ids.index(current)

    chosen_label = safe_radio("Problem", labels, index=index)
    chosen       = options[labels.index(chosen_label)]

    free_text = None
    if chosen["id"] == "other":
        free_text = st.text_area(
            "Describe the problem:", height=70,
            value=engine.answers.get("q2_text", ""),
        )

    col1, col2 = st.columns(2)
    with col1:
        if st.button("← Back", use_container_width=True):
            prev_step("q2")
    with col2:
        if st.button("Next →", type="primary", use_container_width=True):
            engine.record_answer("q2", chosen["id"], free_text)
            go("q3")

# ------------------------------------------------------------------ #
# SCREEN: Q3 — Stakeholder (auto-ordered by domain)
# ------------------------------------------------------------------ #

def screen_q3():
    """
    SCREEN: Q3 — Primary stakeholder selection.
    Options are reordered by domain relevance (most likely role first).
    The selected stakeholder is used in the hypothesis and participant list.
    """
    progress_bar("q3")
    engine = st.session_state.engine
    q      = engine.get_question("q3")

    st.markdown(f"### Q3. {q['text']}")
    st.caption(q.get("help", ""))

    options = engine.get_options("q3")   # domain-ordered
    current = engine.answers.get("q3")
    labels  = [f"{o.get('icon','')}  {o['label']}" for o in options]

    index = 0
    if current:
        ids = [o["id"] for o in options]
        if current in ids:
            index = ids.index(current)

    chosen_label = safe_radio("Stakeholder", labels, index=index)
    chosen       = options[labels.index(chosen_label)]

    if chosen.get("description"):
        st.caption(f"*{chosen['description']}*")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("← Back", use_container_width=True):
            prev_step("q3")
    with col2:
        if st.button("Next →", type="primary", use_container_width=True):
            engine.record_answer("q3", chosen["id"])
            go("q4")

# ------------------------------------------------------------------ #
# SCREEN: Q4 — Current State
# ------------------------------------------------------------------ #

def screen_q4():
    """
    SCREEN: Q4 — Current state / market gap.
    Captures how the problem is handled today (spreadsheets, legacy ERP, competitor, etc.).
    Drives the market_gap dimension score and the McKinsey Horizon classification.
    Also feeds WSJF duration proxy in the scoring engine.
    """
    progress_bar("q4")
    engine = st.session_state.engine
    q      = engine.get_question("q4")

    st.markdown(f"### Q4. {q['text']}")
    st.caption(q.get("help", ""))

    options = engine.get_options("q4")
    current = engine.answers.get("q4")
    labels  = [f"{o.get('icon','')}  {o['label']}" for o in options]

    index = 0
    if current:
        ids = [o["id"] for o in options]
        if current in ids:
            index = ids.index(current)

    chosen_label = safe_radio("Current State", labels, index=index)
    chosen       = options[labels.index(chosen_label)]

    if chosen.get("description"):
        st.caption(f"*{chosen['description']}*")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("← Back", use_container_width=True):
            prev_step("q4")
    with col2:
        if st.button("Next →", type="primary", use_container_width=True):
            engine.record_answer("q4", chosen["id"])
            go("q5")

# ------------------------------------------------------------------ #
# SCREEN: Q5 — Three-factor impact
# ------------------------------------------------------------------ #

def screen_q5():
    """
    SCREEN: Q5 — Three-factor business impact rating.
    Collects: frequency of the problem, severity of its impact, and workaround effort.
    Also includes an optional free-text cost estimate field.
    On submit, calls ScoringEngine.compute() and stores the VerdictResult in session state.
    """
    progress_bar("q5")
    engine  = st.session_state.engine
    q       = engine.get_question("q5")

    st.markdown(f"### Q5. {q['text']}")
    st.caption(q.get("help", ""))

    q5_saved      = engine.answers.get("q5", {}) or {}
    factors       = q.get("factors", [])
    factor_answers = {}

    for factor in factors:
        st.markdown(f"**{factor['icon']} {factor['question']}**")
        opts   = factor["options"]
        labels = [o["label"] for o in opts]
        saved  = q5_saved.get(factor["id"])
        index  = 0
        if saved:
            ids = [o["id"] for o in opts]
            if saved in ids:
                index = ids.index(saved)

        chosen_label              = safe_radio(factor["id"], labels, index=index, key=f"q5_{factor['id']}")
        chosen_opt                = opts[labels.index(chosen_label)]
        factor_answers[factor["id"]] = chosen_opt["id"]
        st.markdown("")

    # ── Optional cost quantification (Phase 1) ──
    st.markdown("---")
    st.markdown("**💰 Estimated cost of this problem** *(optional — used in Research Plan)*")
    st.markdown(
        '<p class="cost-hint">e.g. "~$200K/yr in manual labour", "3 FTE hours per shipment", '
        '"15% margin leakage on tail spend". Leave blank if unknown.</p>',
        unsafe_allow_html=True,
    )
    cost_val = st.text_input(
        "Cost estimate",
        value=st.session_state.get("cost_estimate", ""),
        placeholder="e.g. ~$150K/year in overtime and rework",
        key="cost_estimate_input",
        label_visibility="collapsed",
    )

    col1, col2 = st.columns(2)
    with col1:
        if st.button("← Back", use_container_width=True):
            prev_step("q5")
    with col2:
        if st.button("Get Verdict →", type="primary", use_container_width=True):
            st.session_state.cost_estimate = cost_val
            engine.record_q5(
                factor_answers.get("frequency", ""),
                factor_answers.get("severity", ""),
                factor_answers.get("workaround_effort", ""),
            )
            verdict = st.session_state.scorer.compute(
                engine.answers,
                engine.get_origin_multiplier(),
                engine.is_wip_domain(),
            )
            st.session_state.verdict      = verdict
            st.session_state.idea_recorded = False
            go("verdict")

# ------------------------------------------------------------------ #
# SCREEN: Verdict
# ------------------------------------------------------------------ #

def screen_verdict():
    """
    SCREEN: Verdict — tabbed layout.
    Tabs: Overview · Deep Dive Prompts · Score Breakdown (with Framework Metrics expander) · Domain Audit.
    Domain Knowledge Audit uses org-level predefined config (Electronics, Optimised SC,
    Stable environment, Lumpy/Seasonal/Trigger demand) — config section hidden from team.
    Auto-runs the domain audit on first arrival.
    """
    verdict = st.session_state.verdict
    if not verdict:
        go("idea_input")
        return

    # UCM: record once on first arrival at verdict
    ucm = st.session_state.get("ucm")
    if ucm and not st.session_state.get("idea_recorded", False):
        domain = st.session_state.engine.answers.get("q1", "")
        ucm.record_idea_submitted(
            domain=domain,
            idea_title=st.session_state.idea_title,
            score=verdict.final_score,
            deep_dive=verdict.deep_dive_unlocked,
            answers=dict(st.session_state.engine.answers),
            verdict_dict=verdict.to_dict() if hasattr(verdict, "to_dict") else {},
        )
        st.session_state.idea_recorded = True
        for notif in ucm.get_unlock_notifications():
            st.toast(notif, icon="🔓")

    engine = st.session_state.engine

    # ── Build audit context from org-level config (no user-editable selectors) ──
    audit_ctx = {
        "industry":               ORG_AUDIT_CONFIG["industry"],
        "demand_pattern":         ORG_AUDIT_CONFIG["demand_pattern_primary"],
        "supply_chain_maturity":  ORG_AUDIT_CONFIG["supply_chain_maturity"],
        "disruption_environment": ORG_AUDIT_CONFIG["disruption_environment"],
        "scor_domain":            engine.answers.get("q1", "") if engine else "",
    }

    # ── Auto-run Domain Audit on first visit (if not already cached) ──
    if not st.session_state.get("domain_audit") and not st.session_state.get("_audit_auto_running"):
        st.session_state["_audit_auto_running"] = True
        with st.spinner("🔍 Running Domain Knowledge Audit…"):
            try:
                factory  = st.session_state.get("factory")
                provider = factory.get_provider() if factory else None
                dk_engine = DomainKnowledgeEngine(
                    llm_provider=provider,
                    use_llm=True,
                    industry=audit_ctx["industry"],
                )
                rec_text = (
                    st.session_state.get("idea_description", "")
                    or st.session_state.get("idea_title", "")
                )
                audit_result = dk_engine.evaluate(rec_text, audit_ctx)
                st.session_state.domain_audit     = audit_result
                st.session_state.domain_audit_ctx = audit_ctx
            except Exception as exc:
                st.toast(f"Auto-audit skipped: {exc}", icon="⚠️")
        st.session_state["_audit_auto_running"] = False

    color = verdict.band_color

    demand_display = " · ".join(ORG_AUDIT_CONFIG["demand_patterns_display"])

    # ── Score circle + band card (always visible) ──
    st.markdown(
        f"""<div class="score-circle" style="background:{color}18;border:3px solid {color}">
            <span class="score-number" style="color:{color}">{verdict.percent}</span>
            <span class="score-label" style="color:{color}">/ 100</span>
        </div>""",
        unsafe_allow_html=True,
    )
    band_class = {"high_priority": "green", "promising": "highlight",
                  "needs_clarity": "yellow", "not_ready": "red"}.get(verdict.band, "")
    st.markdown(
        f"""<div class="skout-card {band_class}">
            <div style="font-size:22px;margin-bottom:4px">{verdict.band_emoji}</div>
            <div style="font-size:18px;font-weight:700;color:#0f172a">{verdict.headline}</div>
            <div style="font-size:14px;margin-top:6px;color:#374151">{verdict.message}</div>
        </div>""",
        unsafe_allow_html=True,
    )

    # ── Build decision + stress-test + action plan data ───────────────
    _decision    = _build_decision(verdict)
    _stress_test = _build_stress_test(verdict, engine, st.session_state.get("domain_audit"))
    _action_plan = _build_action_plan(verdict, engine, st.session_state.get("domain_audit"))

    # ── Main tabs ──────────────────────────────────────────────────────
    audit = st.session_state.get("domain_audit")
    audit_tab_label = (
        f"🧠 Domain Audit · {audit.overall_verdict}" if audit else "🧠 Domain Audit"
    )
    tab_overview, tab_prompts, tab_score_bd, tab_dmaic, tab_audit = st.tabs([
        "🎯 Decision & Plan",
        "🔬 Stress-Test Hypothesis",
        "📊 Score Breakdown",
        "📐 DMAIC Canvas",
        audit_tab_label,
    ])

    # ══════════════════════════════════════════════════════════════════
    # TAB 1 — DECISION & ACTION PLAN
    # ══════════════════════════════════════════════════════════════════
    with tab_overview:

        # ── 1. Decision banner ────────────────────────────────────────
        d = _decision

        # ── Horizon pill + Benchmark row — right below the GO/REFINE/STOP banner ──
        q2_val     = engine.answers.get("q2", "") if engine else ""
        q4_val     = engine.answers.get("q4", "") if engine else ""
        domain_ctx = engine.answers.get("q1", "") if engine else ""
        if q2_val or q4_val:
            h_code, h_label, h_bg, h_text_color, h_desc = get_horizon(verdict.band, q4_val, q2_val)
            bm = get_benchmark(ucm, domain_ctx, verdict.final_score)
            _hcol, _bcol = st.columns([3, 2])
            with _hcol:
                st.markdown(
                    f'<span class="horizon-pill" style="background:{h_bg};color:{h_text_color}">'
                    f'{h_code} · {h_label}</span>'
                    f'<div class="horizon-desc" style="margin-top:4px">{h_desc}</div>',
                    unsafe_allow_html=True,
                )
            with _bcol:
                if bm:
                    st.markdown(
                        f'<div class="benchmark-row">'
                        f'<div style="font-size:11px;font-weight:700;color:#64748b;'
                        f'text-transform:uppercase;letter-spacing:0.5px;margin-bottom:4px">'
                        f'Your Benchmark</div>'
                        f'<span class="benchmark-pct">{bm["percentile"]}th</span>'
                        f'<span style="font-size:12px;color:#6b7280"> percentile</span>'
                        f'<div style="font-size:11px;color:#94a3b8;margin-top:2px">'
                        f'vs {bm["count"]} ideas · {bm["scope"]}</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

        # ── Decision banner ───────────────────────────────────────────
        st.markdown(
            f'<div style="background:{d["bg"]};border:2px solid {d["border"]};border-radius:12px;'
            f'padding:20px 24px;margin-bottom:16px;margin-top:12px">'
            f'<div style="display:flex;align-items:center;gap:12px;margin-bottom:10px">'
            f'<span style="font-size:36px">{d["emoji"]}</span>'
            f'<span style="font-size:28px;font-weight:800;color:{d["color"]};letter-spacing:-0.5px">'
            f'{d["label"]}</span>'
            f'</div>'
            f'<div style="font-size:14px;color:#374151;line-height:1.6">{d["rationale"]}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        # JTBD Problem Statement (compact, always show)
        if engine and engine.answers.get("q2"):
            jtbd = get_jtbd_statement(engine)
            st.markdown(
                f'<div class="jtbd-box" style="margin-bottom:14px">'
                f'<div class="jtbd-label">📌 JTBD Problem Statement</div>'
                f'{jtbd}'
                f'</div>',
                unsafe_allow_html=True,
            )

        # Confidence flags (compact strip)
        for flag in verdict.confidence_flags:
            ftype = flag.get("type", "info")
            css   = {"warning": "flag-warning", "info": "flag-info", "caution": "flag-caution"}.get(ftype, "flag-info")
            st.markdown(f'<div class="{css}">{flag["message"]}</div>', unsafe_allow_html=True)

        # Cost estimate pill
        cost_est = st.session_state.get("cost_estimate", "").strip()
        if cost_est:
            st.markdown(
                f'<div style="background:#fefce8;border:1px solid #fbbf24;border-radius:8px;'
                f'padding:8px 14px;font-size:13px;color:#713f12;margin:8px 0">'
                f'💰 <strong>Estimated cost impact:</strong> {cost_est}'
                f'</div>',
                unsafe_allow_html=True,
            )

        st.divider()

        # ── 2. Action Plan ────────────────────────────────────────────
        st.markdown(
            '<div style="font-size:15px;font-weight:700;color:#0f172a;margin-bottom:12px">'
            '✅ Action Plan</div>',
            unsafe_allow_html=True,
        )

        tag_colors = {
            "NOW":   ("#dcfce7", "#15803d"),
            "NEXT":  ("#fefce8", "#b45309"),
            "LATER": ("#f0f9ff", "#0369a1"),
        }

        for i, step in enumerate(_action_plan, 1):
            tag   = step.get("tag", "NEXT")
            tc_bg, tc_fg = tag_colors.get(tag, ("#f1f5f9", "#475569"))
            owner = step.get("owner", "PM")
            st.markdown(
                f'<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;'
                f'padding:14px 16px;margin-bottom:10px;display:flex;gap:14px;align-items:flex-start">'
                f'<div style="min-width:28px;height:28px;background:#6366f1;border-radius:50%;'
                f'display:flex;align-items:center;justify-content:center;'
                f'font-size:13px;font-weight:700;color:white;flex-shrink:0">{i}</div>'
                f'<div style="flex:1">'
                f'<div style="font-size:14px;font-weight:600;color:#0f172a;margin-bottom:4px">'
                f'{step["step"]}</div>'
                f'<div style="font-size:12px;color:#64748b;line-height:1.5">{step["why"]}</div>'
                f'<div style="margin-top:8px;display:flex;gap:8px;flex-wrap:wrap">'
                f'<span style="background:{tc_bg};color:{tc_fg};font-size:11px;font-weight:700;'
                f'padding:2px 8px;border-radius:4px">{tag}</span>'
                f'<span style="background:#f1f5f9;color:#475569;font-size:11px;'
                f'padding:2px 8px;border-radius:4px">👤 {owner}</span>'
                f'</div>'
                f'</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    # ══════════════════════════════════════════════════════════════════
    # TAB 2 — STRESS-TEST HYPOTHESIS
    # ══════════════════════════════════════════════════════════════════
    with tab_prompts:
        st.markdown(
            '<div style="font-size:13px;color:#64748b;margin-bottom:16px">'
            'These questions target your weakest scoring dimensions. Answer each one to sharpen '
            'your hypothesis — then use the AI prompt to go deeper.</div>',
            unsafe_allow_html=True,
        )

        for idx, item in enumerate(_stress_test):
            pct   = item["pct"]
            dim   = item["dimension"]
            bar_color = "#dc2626" if pct < 40 else ("#ca8a04" if pct < 65 else "#16a34a")

            # Dimension header with mini score bar
            st.markdown(
                f'<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;'
                f'padding:16px 18px;margin-bottom:14px">'
                f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">'
                f'<span style="font-size:13px;font-weight:700;color:#0f172a">{dim}</span>'
                f'<span style="font-size:12px;font-weight:700;color:{bar_color}">{pct}%</span>'
                f'</div>'
                f'<div style="background:#e5e7eb;border-radius:4px;height:5px;margin-bottom:14px">'
                f'<div style="background:{bar_color};width:{pct}%;height:5px;border-radius:4px"></div>'
                f'</div>'
                f'<div style="font-size:13px;font-weight:600;color:#1e40af;margin-bottom:8px">'
                f'❓ {item["question"]}</div>'
                f'<div style="font-size:12px;color:#64748b;font-style:italic">'
                f'Answer this before your next stakeholder conversation.</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

            # Expandable AI prompt
            with st.expander(f"🤖 AI prompt to help answer this — {dim}", expanded=False):
                st.markdown(
                    '<div style="font-size:12px;color:#6b7280;margin-bottom:8px">'
                    'Copy this into Claude or ChatGPT for a detailed analysis:</div>',
                    unsafe_allow_html=True,
                )
                st.code(item["ai_prompt"], language=None)
                st.caption("Tip: add your specific context (org name, data systems, team size) before sending.")

    # ══════════════════════════════════════════════════════════════════
    # TAB 3 — SCORE BREAKDOWN (includes framework metrics)
    # ══════════════════════════════════════════════════════════════════
    with tab_score_bd:
        dim_labels = {
            "business_impact":   "Business Impact (Q5)",
            "problem_clarity":   "Problem Clarity (Q2)",
            "market_gap":        "Market Gap (Q4)",
            "stakeholder_reach": "Stakeholder Reach (Q3)",
            "domain_fit":        "Domain Fit (Q1)",
        }
        dim_colors = {
            "business_impact":   "#f59e0b",
            "problem_clarity":   "#8b5cf6",
            "market_gap":        "#06b6d4",
            "stakeholder_reach": "#10b981",
            "domain_fit":        "#6366f1",
        }
        for dim, score in verdict.dimension_scores.items():
            max_pts   = verdict.dimension_max.get(dim, 30)
            pct       = int((score / max_pts) * 100) if max_pts else 0
            label     = dim_labels.get(dim, dim)
            col_color = dim_colors.get(dim, "#6366f1")
            st.markdown(
                f"""<div style="margin-bottom:10px">
                    <div style="display:flex;justify-content:space-between;font-size:13px;color:#0f172a">
                        <span>{label}</span>
                        <span style="font-weight:700">{score:.0f}/{max_pts}</span>
                    </div>
                    <div class="dim-bar-bg">
                        <div class="dim-bar" style="width:{pct}%;background:{col_color}"></div>
                    </div>
                </div>""",
                unsafe_allow_html=True,
            )
        st.markdown(
            f"**Origin multiplier:** ×{verdict.origin_multiplier} &nbsp;|&nbsp; "
            f"**Base:** {verdict.base_score:.1f} → **Final:** {verdict.final_score:.1f}"
        )

        st.divider()

        # Ideas Like This
        _domain  = engine.answers.get("q1", "") if engine else ""
        _problem = engine.answers.get("q2", "") if engine else ""
        if _domain:
            _similar = IdeasLikeThis().find(
                current_domain=_domain,
                current_score=verdict.final_score,
                current_title=st.session_state.idea_title,
                current_description=st.session_state.idea_description,
                current_problem=_problem,
                top_n=3,
            )
            _pattern_msg = IdeasLikeThis().get_pattern_summary(_domain, verdict.final_score)
            if _similar or _pattern_msg:
                with st.expander(
                    "🔎 Ideas Like This (" + str(len(_similar)) + " similar in your history)",
                    expanded=False,
                ):
                    if _pattern_msg:
                        st.info(_pattern_msg)
                    for _s in _similar:
                        _outcome_tag = f" · _{_s.outcome}_" if _s.outcome else ""
                        _deep_tag    = " · 🔬 deep-dived" if _s.deep_dive else ""
                        st.markdown(
                            '<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;'
                            'padding:10px 14px;margin-bottom:8px;font-size:13px">'
                            + f"<strong>{_s.title}</strong> &nbsp; "
                            + f'<span style="color:#6366f1;font-weight:700">{int(_s.score)}/100</span> · '
                            + f'<span style="color:#64748b">{_s.band_label}</span> · '
                            + f'<span style="color:#94a3b8">{_s.date}</span>{_outcome_tag}{_deep_tag}<br/>'
                            + f'<span style="font-size:11px;color:#9ca3af">'
                            + f'Similarity: {_s.similarity_score:.0%} — {_s.similarity_reason}</span>'
                            + '</div>',
                            unsafe_allow_html=True,
                        )

        # Framework metrics — folded into Score Breakdown as an expander
        with st.expander("📐 Framework Metrics (SCOR · WSJF · ODI)", expanded=False):
            _scor = verdict.scor_category
            _wsjf = verdict.wsjf_score
            _opp  = verdict.opportunity_gap

            st.markdown(
                f'<div style="margin-bottom:14px">'
                f'<div style="font-size:11px;font-weight:700;color:#64748b;'
                f'text-transform:uppercase;letter-spacing:0.5px;margin-bottom:6px">SCOR Framework Alignment</div>'
                f'<span class="scor-pill">{verdict.scor_icon} {_scor}</span>'
                f'<div style="font-size:12px;color:#64748b;margin-top:5px">{verdict.scor_description}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

            wsjf_color = "#16a34a" if _wsjf >= 7 else ("#ca8a04" if _wsjf >= 4 else "#64748b")
            opp_color  = "#16a34a" if _opp  >= 14 else ("#ca8a04" if _opp  >= 8  else "#64748b")
            wsjf_band  = "High urgency" if _wsjf >= 7 else ("Moderate" if _wsjf >= 4 else "Low urgency")
            opp_band   = "Underserved" if _opp >= 14 else ("Moderate gap" if _opp >= 8 else "Well-served")

            st.markdown(
                f'<div class="metrics-strip">'
                f'<div class="metric-card">'
                f'<div class="metric-card-label">WSJF Urgency</div>'
                f'<div class="metric-card-value" style="color:{wsjf_color}">{_wsjf:.1f}'
                f'<span style="font-size:13px;color:#94a3b8"> /10</span></div>'
                f'<div class="metric-card-sub">{wsjf_band}</div>'
                f'</div>'
                f'<div class="metric-card">'
                f'<div class="metric-card-label">Opportunity Gap</div>'
                f'<div class="metric-card-value" style="color:{opp_color}">{_opp:.1f}'
                f'<span style="font-size:13px;color:#94a3b8"> /20</span></div>'
                f'<div class="metric-card-sub">{opp_band}</div>'
                f'</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
            st.caption(
                "**WSJF** = Cost of Delay ÷ Duration proxy — higher = delay cost outweighs build effort. "
                "**ODI Opportunity Gap** = Importance + max(Importance − Satisfaction, 0) — "
                "≥14 signals an underserved problem worth prioritising."
            )

    # ══════════════════════════════════════════════════════════════════
    # TAB 4 — DMAIC CANVAS
    # ══════════════════════════════════════════════════════════════════
    with tab_dmaic:
        _canvas_exists = st.session_state.get("dmaic_canvas")
        if not _canvas_exists:
            st.markdown(
                '<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;'
                'padding:20px 24px;text-align:center;margin-bottom:16px">'
                '<div style="font-size:32px;margin-bottom:8px">📐</div>'
                '<div style="font-size:15px;font-weight:700;color:#0f172a;margin-bottom:6px">'
                'DMAIC Canvas</div>'
                '<div style="font-size:13px;color:#64748b;margin-bottom:16px">'
                'Translate your Q1–Q5 answers into a structured Define / Measure / Analyze / '
                'Improve / Control problem-solving canvas.</div>'
                '</div>',
                unsafe_allow_html=True,
            )
            if st.button("🔨 Generate DMAIC Canvas", type="primary", use_container_width=True, key="build_dmaic_tab"):
                with st.spinner("Building canvas…"):
                    _canvas = DMAICEngine().build(
                        answers=st.session_state.engine.answers,
                        idea_title=st.session_state.idea_title,
                        idea_description=st.session_state.idea_description,
                        research_plan=st.session_state.get("research_plan"),
                        verdict_score=verdict.final_score,
                    )
                    st.session_state.dmaic_canvas = _canvas
                st.rerun()
        else:
            _c = st.session_state.dmaic_canvas
            st.success("✅ DMAIC Canvas generated")
            st.download_button(
                "📄 Download Canvas (.md)",
                data=_c.to_markdown(),
                file_name="dmaic_canvas.md",
                mime="text/markdown",
                use_container_width=True,
                key="dl_dmaic_verdict",
            )
            st.divider()
            # Render each DMAIC phase inline
            _phase_icons = {"Define": "🎯", "Measure": "📏", "Analyze": "🔍",
                            "Improve": "⚙️", "Control": "🛡️"}
            for _phase in ["Define", "Measure", "Analyze", "Improve", "Control"]:
                _content = getattr(_c, _phase.lower(), None)
                if _content:
                    _icon = _phase_icons.get(_phase, "")
                    with st.expander(f"{_icon} {_phase}", expanded=(_phase == "Define")):
                        if isinstance(_content, dict):
                            for _k, _v in _content.items():
                                st.markdown(f"**{_k}:** {_v}")
                        else:
                            st.markdown(str(_content))
            if st.button("🔄 Regenerate Canvas", key="regen_dmaic", use_container_width=False):
                with st.spinner("Rebuilding…"):
                    _canvas = DMAICEngine().build(
                        answers=st.session_state.engine.answers,
                        idea_title=st.session_state.idea_title,
                        idea_description=st.session_state.idea_description,
                        research_plan=st.session_state.get("research_plan"),
                        verdict_score=verdict.final_score,
                    )
                    st.session_state.dmaic_canvas = _canvas
                st.rerun()

    # ══════════════════════════════════════════════════════════════════
    # TAB 5 — DOMAIN AUDIT
    # ══════════════════════════════════════════════════════════════════
    with tab_audit:
        # ── Audit TL;DR — surface the headline finding immediately ──
        _audit_now = st.session_state.get("domain_audit")
        if _audit_now:
            _top_ch  = _audit_now.challenges[0] if getattr(_audit_now, "challenges", None) else None
            _top_kpi = _audit_now.kpi_warnings[0] if getattr(_audit_now, "kpi_warnings", None) else None
            _col_a, _col_b = st.columns(2)
            with _col_a:
                if _top_ch:
                    _bc = {"CRITICAL": "#dc2626", "HIGH": "#ea580c",
                           "MEDIUM": "#ca8a04", "LOW": "#16a34a"}.get(_top_ch.severity, "#6b7280")
                    st.markdown(
                        f'<div style="background:{_bc}0f;border-left:4px solid {_bc};'
                        f'border-radius:6px;padding:10px 14px;font-size:12px">'
                        f'<div style="font-weight:700;color:{_bc};margin-bottom:3px">'
                        f'⚔️ Top challenge · {_top_ch.severity}</div>'
                        f'<div style="color:#374151">{_top_ch.name}</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                else:
                    st.success("⚔️ No critical challenges flagged")
            with _col_b:
                if _top_kpi:
                    _kc = {"RED": "#dc2626", "AMBER": "#ca8a04",
                           "INFO": "#2563eb"}.get(_top_kpi.severity, "#6b7280")
                    st.markdown(
                        f'<div style="background:{_kc}0f;border-left:4px solid {_kc};'
                        f'border-radius:6px;padding:10px 14px;font-size:12px">'
                        f'<div style="font-weight:700;color:{_kc};margin-bottom:3px">'
                        f'📊 Top KPI gap · {_top_kpi.severity}</div>'
                        f'<div style="color:#374151">{_top_kpi.kpi_name}</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                else:
                    st.success("📊 No KPI benchmark violations")
            st.markdown("")  # spacer

        # Org config read-only badge
        st.markdown(
            f'<div style="background:#f0fdf4;border:1px solid #86efac;border-radius:8px;'
            f'padding:10px 16px;margin-bottom:14px;font-size:12px;color:#15803d">'
            f'<strong>🏢 Org-level audit config</strong> &nbsp;·&nbsp; '
            f'SC Maturity: <strong>Optimised</strong> &nbsp;·&nbsp; '
            f'Environment: <strong>Stable</strong> &nbsp;·&nbsp; '
            f'Demand: <strong>{demand_display}</strong>'
            f'</div>',
            unsafe_allow_html=True,
        )

        if st.button("🔄 Re-run Domain Knowledge Audit", type="secondary", use_container_width=True):
            with st.spinner("Running 7 domain knowledge patterns…"):
                try:
                    factory  = st.session_state.get("factory")
                    provider = factory.get_provider() if factory else None
                    dk_engine = DomainKnowledgeEngine(
                        llm_provider=provider,
                        use_llm=True,
                        industry=audit_ctx["industry"],
                    )
                    rec_text = (
                        st.session_state.get("idea_description", "")
                        or st.session_state.get("idea_title", "")
                    )
                    audit_result = dk_engine.evaluate(rec_text, audit_ctx)
                    st.session_state.domain_audit     = audit_result
                    st.session_state.domain_audit_ctx = audit_ctx
                    st.rerun()
                except Exception as exc:
                    st.error(f"Audit error: {exc}")

        audit = st.session_state.get("domain_audit")
        if audit:
            v_color = audit.verdict_color
            st.markdown(
                f'<div style="background:{v_color}18;border-left:4px solid {v_color};'
                f'border-radius:8px;padding:14px 18px;margin:12px 0">'
                f'<div style="font-size:22px;font-weight:800;color:{v_color}">'
                f'{audit.verdict_emoji} {audit.overall_verdict}</div>'
                f'<div style="font-size:13px;color:#374151;margin-top:4px">'
                f'Risk level: <strong style="color:{audit.risk_color}">{audit.risk_level}</strong> &nbsp;|&nbsp; '
                f'{audit.reasoning}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

            # Inner audit tabs
            a_tab_ch, a_tab_kpi, a_tab_score, a_tab_ctx, a_tab_rag = st.tabs([
                f"⚔️ Challenges ({audit.challenger_summary.get('total', 0)})",
                f"📊 KPI Warnings ({len(audit.kpi_warnings)})",
                "📐 Domain Score",
                "🌍 Context Check",
                "📚 Knowledge Retrieved",
            ])

            with a_tab_ch:
                if audit.scor_risks:
                    st.markdown(f"**SCOR Domain: {audit.scor_domain.title()}** — Known risks in this domain:")
                    for r in audit.scor_risks:
                        st.markdown(f"- {r}")
                    st.divider()
                if not audit.challenges:
                    st.success("No failure patterns detected in rule-based scan.")
                else:
                    for c in audit.challenges:
                        badge_color = {"CRITICAL": "#dc2626", "HIGH": "#ea580c", "MEDIUM": "#ca8a04", "LOW": "#16a34a"}.get(c.severity, "#6b7280")
                        st.markdown(
                            f'<div style="border-left:3px solid {badge_color};padding:8px 12px;margin:6px 0;background:#f9fafb;border-radius:4px">'
                            f'<strong style="color:{badge_color}">{c.severity_emoji} {c.severity} — {c.name}</strong><br>'
                            f'<span style="font-size:13px;color:#374151">{c.description}</span>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )
                        if c.challenge_questions:
                            with st.expander("Challenge questions to answer →"):
                                for q in c.challenge_questions:
                                    st.markdown(f"❓ {q}")
                        if c.example_failure:
                            with st.expander("Real-world failure example →"):
                                st.caption(c.example_failure)

            with a_tab_kpi:
                if not audit.kpi_warnings:
                    st.success("No KPI benchmark violations detected.")
                else:
                    for w in audit.kpi_warnings:
                        sev_color = {"RED": "#dc2626", "AMBER": "#ca8a04", "INFO": "#2563eb"}.get(w.severity, "#6b7280")
                        st.markdown(
                            f'<div style="border-left:3px solid {sev_color};padding:8px 12px;margin:6px 0;background:#f9fafb;border-radius:4px">'
                            f'<strong style="color:{sev_color}">{w.severity_emoji} {w.kpi_name}</strong><br>'
                            f'<span style="font-size:13px">{w.message}</span><br>'
                            f'<span style="font-size:12px;color:#6b7280;margin-top:4px;display:block">💡 {w.recommendation}</span>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )

            with a_tab_score:
                ds = audit.domain_score
                score_col1, score_col2 = st.columns([1, 2])
                with score_col1:
                    sc_color = ds.verdict_color
                    st.markdown(
                        f'<div style="background:{sc_color}18;border:2px solid {sc_color};border-radius:50%;'
                        f'width:110px;height:110px;display:flex;flex-direction:column;align-items:center;'
                        f'justify-content:center;margin:0 auto">'
                        f'<div style="font-size:28px;font-weight:800;color:{sc_color}">{ds.score_pct}%</div>'
                        f'<div style="font-size:11px;color:#6b7280">{ds.verdict}</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                with score_col2:
                    from core.domain_scorer import DIMENSION_LABELS
                    for dim, label in DIMENSION_LABELS.items():
                        score_val = ds.dimension_scores.get(dim, 0.0)
                        if dim in ("cost_impact", "resilience_impact", "service_level_impact"):
                            bar_val   = (score_val + 1.0) / 2.0
                            display   = f"{score_val:+.2f}"
                            bar_color = "#16a34a" if score_val > 0.2 else ("#dc2626" if score_val < -0.2 else "#ca8a04")
                        else:
                            bar_val   = score_val
                            display   = f"{score_val:.2f}"
                            bar_color = "#2563eb"
                        bar_pct = int(bar_val * 100)
                        st.markdown(
                            f'<div style="margin-bottom:8px">'
                            f'<div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:2px">'
                            f'<span>{label}</span><span style="color:{bar_color};font-weight:700">{display}</span></div>'
                            f'<div style="background:#e5e7eb;border-radius:4px;height:6px">'
                            f'<div style="background:{bar_color};width:{bar_pct}%;height:6px;border-radius:4px"></div>'
                            f'</div></div>',
                            unsafe_allow_html=True,
                        )
                if ds.tradeoffs:
                    st.markdown("**Key tradeoffs identified:**")
                    for t in ds.tradeoffs:
                        st.markdown(f"↔️ {t}")
                if ds.blocking_reason:
                    st.error(f"🚫 Blocking reason: {ds.blocking_reason}")

            with a_tab_ctx:
                cc = audit.context_check
                completeness_color = "#16a34a" if cc.completeness_pct >= 80 else ("#ca8a04" if cc.completeness_pct >= 50 else "#dc2626")
                st.markdown(
                    f'<div style="font-size:13px;margin-bottom:10px">'
                    f'Context completeness: <strong style="color:{completeness_color}">{cc.completeness_pct}%</strong> '
                    f'— {cc.verdict_emoji} {cc.verdict}</div>',
                    unsafe_allow_html=True,
                )
                if cc.risk_combo_warnings:
                    for warning in cc.risk_combo_warnings:
                        st.warning(f"⚠️ High-risk combination: {warning}")
                if cc.missing_critical:
                    st.error(f"🔴 Missing critical context: {', '.join(cc.missing_critical)}")
                if cc.missing_important:
                    st.warning(f"🟡 Missing important context: {', '.join(cc.missing_important)}")
                if cc.missing_helpful:
                    st.info(f"🔵 Optional context not provided: {', '.join(cc.missing_helpful)}")
                if cc.questions_to_ask:
                    with st.expander(f"📋 {len(cc.questions_to_ask)} context gap(s) to fill →"):
                        for q in cc.questions_to_ask[:5]:
                            st.markdown(
                                f"{'🔴' if q['tier']=='CRITICAL' else '🟡'} **{q['question']}**  \n"
                                f"<span style='font-size:12px;color:#6b7280'>{q['hint']}</span>  \n"
                                f"<span style='font-size:11px;color:#9ca3af'>Why: {q['why']}</span>",
                                unsafe_allow_html=True,
                            )

            with a_tab_rag:
                if not audit.rag_chunks:
                    st.info("No domain knowledge chunks retrieved.")
                else:
                    st.caption(f"Retrieved {len(audit.rag_chunks)} relevant knowledge chunks:")
                    for chunk in audit.rag_chunks:
                        cat_emoji = {"scor": "🏗️", "kpi": "📊", "failure_pattern": "⚠️"}.get(chunk.category, "📄")
                        relevance_pct = int(chunk.relevance * 100)
                        with st.expander(f"{cat_emoji} {chunk.source} — relevance {relevance_pct}%"):
                            st.markdown(f"```\n{chunk.content[:500]}\n```")

            if audit.action_items:
                st.markdown("**📋 Action items to address before proceeding:**")
                for i, item in enumerate(audit.action_items[:6], 1):
                    st.markdown(f"{i}. {item}")
        else:
            st.info("Domain audit is running — please wait or click Re-run above.")

    # ── Final navigation (outside tabs) ──
    st.divider()

    # ══════════════════════════════════════════════════════════════════
    # LOG FINDINGS — inline form
    # ══════════════════════════════════════════════════════════════════
    st.markdown(
        '<div style="font-size:15px;font-weight:700;color:#0f172a;margin-bottom:4px">'
        '📝 Log Your Findings</div>'
        '<div style="font-size:13px;color:#64748b;margin-bottom:14px">'
        'Record what you learned from discovery, stakeholder conversations, or research. '
        'Saved findings travel with this idea.</div>',
        unsafe_allow_html=True,
    )

    _existing = st.session_state.get("idea_findings", {})

    _hyp_status = st.radio(
        "Hypothesis status",
        ["🟢 Confirmed", "🟡 Partially confirmed", "🔴 Refuted", "⚪ Still open"],
        index=["🟢 Confirmed", "🟡 Partially confirmed", "🔴 Refuted", "⚪ Still open"].index(
            _existing.get("hyp_status", "⚪ Still open")
        ),
        horizontal=True,
        key="findings_hyp_status",
    )

    _col_f1, _col_f2 = st.columns(2)
    with _col_f1:
        _key_finding = st.text_area(
            "Key finding",
            value=_existing.get("key_finding", ""),
            height=100,
            placeholder="What did you learn? What evidence supports or challenges the hypothesis?",
            key="findings_key_finding",
        )
    with _col_f2:
        _main_risk = st.text_area(
            "Main risk identified",
            value=_existing.get("main_risk", ""),
            height=100,
            placeholder="What is the single biggest risk or blocker? Who owns mitigating it?",
            key="findings_main_risk",
        )

    _outcome_tag = st.selectbox(
        "Outcome tag",
        ["— select —", "✅ Validated", "⚠️ At risk", "🗄️ Parked", "🚀 Approved to scope"],
        index=["— select —", "✅ Validated", "⚠️ At risk", "🗄️ Parked", "🚀 Approved to scope"].index(
            _existing.get("outcome_tag", "— select —")
        ) if _existing.get("outcome_tag", "— select —") in [
            "— select —", "✅ Validated", "⚠️ At risk", "🗄️ Parked", "🚀 Approved to scope"
        ] else 0,
        key="findings_outcome_tag",
    )

    _save_col, _clear_col = st.columns([3, 1])
    with _save_col:
        if st.button("💾 Save findings", type="primary", use_container_width=True, key="save_findings_btn"):
            _findings_data = {
                "hyp_status":  _hyp_status,
                "key_finding": _key_finding.strip(),
                "main_risk":   _main_risk.strip(),
                "outcome_tag": _outcome_tag if _outcome_tag != "— select —" else "",
                "saved_at":    __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M"),
                "idea_title":  st.session_state.get("idea_title", ""),
                "score":       verdict.final_score,
            }
            st.session_state["idea_findings"] = _findings_data
            # Also persist into UCM if available
            _ucm_ref = st.session_state.get("ucm")
            if _ucm_ref and hasattr(_ucm_ref, "record_finding"):
                try:
                    _ucm_ref.record_finding(_findings_data)
                except Exception:
                    pass
            st.toast("Findings saved ✅", icon="📝")
            st.rerun()
    with _clear_col:
        if st.button("🗑️ Clear", use_container_width=True, key="clear_findings_btn"):
            st.session_state["idea_findings"] = {}
            st.rerun()

    # Show saved badge if findings exist
    if _existing.get("saved_at"):
        st.markdown(
            f'<div style="background:#f0fdf4;border:1px solid #86efac;border-radius:8px;'
            f'padding:10px 14px;font-size:12px;color:#15803d;margin-top:6px">'
            f'✅ Findings saved · {_existing["saved_at"]} · '
            f'<strong>{_existing.get("outcome_tag","")}</strong></div>',
            unsafe_allow_html=True,
        )

    st.divider()

    # Refine Problem Description — inline editor, preserves all Q1/Q3/Q4/Q5 answers and score weights
    with st.expander("✏️ Refine problem description", expanded=False):
        st.caption(
            "Update how you've described the problem without changing the scored answers. "
            "This refreshes the JTBD statement and domain audit context — it does not alter your score."
        )
        _current_desc = st.session_state.get("idea_description", "")
        _new_desc = st.text_area(
            "Problem description",
            value=_current_desc,
            height=110,
            key="refine_desc_input",
            label_visibility="collapsed",
            placeholder="Describe the problem your idea addresses…",
        )
        if st.button("💾 Save & refresh", key="save_refined_desc", use_container_width=True):
            if _new_desc.strip() and _new_desc.strip() != _current_desc:
                st.session_state.idea_description = _new_desc.strip()
                # Clear audit so it re-runs with new description on next render
                st.session_state.domain_audit = None
                st.session_state["_audit_auto_running"] = False
                st.toast("Problem description updated — re-running audit…", icon="✅")
                st.rerun()
            else:
                st.info("No changes to save.")

    col_nav1, col_nav2 = st.columns(2)
    with col_nav1:
        st.caption("")  # spacer — Reevaluate removed to prevent score manipulation via Q1–Q5
    with col_nav2:
        if verdict.deep_dive_unlocked:
            if st.button("🔬 Open Research Plan →", type="primary", use_container_width=True):
                go("research_plan")
        else:
            st.info(f"Score {verdict.deep_think_threshold}+ unlocks the Research Plan. Your score: {verdict.percent}.")


def screen_research_plan():
    verdict = st.session_state.verdict
    engine  = st.session_state.engine
    ucm     = st.session_state.get("ucm")

    st.markdown("## 🔬 Research Plan")
    st.markdown(f"**{st.session_state.idea_title}** · {verdict.band_emoji} {verdict.percent}/100")
    st.divider()

    # Mode selector
    factory   = st.session_state.factory
    provider  = factory.get_provider()
    from llm.factory import RuleBasedProvider
    is_rule_based = isinstance(provider, RuleBasedProvider)

    if is_rule_based:
        st.info("ℹ️ No API key detected — running in rule-based mode. Set `ANTHROPIC_API_KEY` in your `.env` to enable LLM enrichment.")
        mode = "quick_scan"
    else:
        mode_choice = st.radio(
            "Research depth:",
            ["🤖 Standard (Haiku, ~15s)", "🧠 Deep Research (Sonnet + extended thinking, ~60s)"],
            horizontal=True,
        )
        mode = "deep_research" if "Deep" in mode_choice else "standard"
        if mode == "deep_research":
            st.info("🧠 Generates 3 competing hypotheses, counter-arguments, and second-order effects.")

    regen = st.button("🔄 Regenerate", use_container_width=False)
    if st.session_state.research_plan is None or regen:
        with st.spinner("Product Skout is thinking…" if mode == "deep_research" else "Generating plan…"):
            planner = ResearchPlanner(provider=provider)
            plan = planner.generate(
                answers=engine.answers,
                verdict=verdict,
                idea_title=st.session_state.idea_title,
                idea_description=st.session_state.idea_description,
                mode=mode,
                cost_estimate=st.session_state.get("cost_estimate", ""),
            )
            if ucm:
                plan = ucm.inject_into_plan(plan)
                methods_used = [m.get("method", "") for m in plan.get("research_methods", []) if m.get("method")]
                if methods_used:
                    ucm.record_research_completed(methods_used)
            st.session_state.research_plan = plan
            st.session_state.research_mode = mode

    plan = st.session_state.research_plan
    if not plan:
        st.error("Could not generate research plan.")
        return

    # ---- Plan-at-a-glance summary card ----
    n_qs  = len(plan.get("interview_questions", []))
    n_pax = len(plan.get("participants", []))
    n_sig = len(plan.get("data_signals", []))
    n_cri = len(plan.get("success_criteria", []))
    hyp_preview = (plan.get("hypothesis") or "")[:120]
    if len(plan.get("hypothesis", "")) > 120:
        hyp_preview += "…"

    source = plan.get("source", "")
    source_badge = ("🧠 Deep Research" if source.startswith("llm_deep")
                    else ("🤖 LLM-enriched" if source.startswith("llm")
                    else "📋 Rule-based"))

    if ucm:
        org = ucm.get_org_context()
        org_note = f" · {org.get('type','')} · {org.get('size','')}" if org.get("type") else ""
    else:
        org_note = ""

    cost_est_display = plan.get("cost_estimate", "").strip()
    cost_html = (
        f"<div style='font-size:12px;color:#713f12;margin-top:6px'>"
        f"💰 <strong>Cost estimate:</strong> {cost_est_display}</div>"
        if cost_est_display else ""
    )

    st.markdown(
        f"""<div class="plan-summary">
          <div style="font-size:11px;font-weight:700;color:#4c1d95;text-transform:uppercase;margin-bottom:8px">
            {source_badge}{org_note}
          </div>
          <div style="margin-bottom:8px">
            <span class="plan-stat">❓ {n_qs} interview questions</span>
            <span class="plan-stat">👥 {n_pax} participant type(s)</span>
            <span class="plan-stat">📊 {n_sig} data signals</span>
            <span class="plan-stat">✅ {n_cri} success criteria</span>
          </div>
          {"<div style='font-size:12px;color:#3730a3;font-style:italic'>" + hyp_preview + "</div>" if hyp_preview else ""}
          {cost_html}
        </div>""",
        unsafe_allow_html=True,
    )

    # Quick-proceed option
    col_skip1, col_skip2 = st.columns([2, 1])
    with col_skip2:
        if st.button("⏭️ Skip to Findings →", use_container_width=True):
            go("findings")

    st.markdown("")

    # ---- Tabbed content ----
    tab_overview, tab_interviews, tab_data, tab_methods = st.tabs([
        "📋 Overview", "👥 Interviews", "📊 Data & Evidence", "🗓️ Methods"
    ])

    # ── Tab 1: Overview ──────────────────────────────────────────────
    with tab_overview:
        if plan.get("competing_hypotheses"):
            st.markdown("#### 🔀 Competing Hypotheses")
            for i, hyp in enumerate(plan["competing_hypotheses"]):
                card_class = "primary" if i == 0 else ""
                conf       = hyp.get("confidence", "medium")
                conf_class = f"hyp-conf-{conf}"
                label      = ["Primary", "Alternative", "Contrarian"][i] if i < 3 else f"#{i+1}"
                st.markdown(
                    f"""<div class="hyp-card {card_class}">
                        <div style="font-size:11px;font-weight:700;color:#6b7280;text-transform:uppercase;margin-bottom:4px">
                            {label} · <span class="{conf_class}">{conf.upper()} CONFIDENCE</span>
                        </div>
                        <div style="font-size:13px;line-height:1.6;color:#111827">{hyp['hypothesis']}</div>
                        <div style="font-size:11px;color:#6b7280;margin-top:6px">
                            ✓ {hyp.get('evidence_for','')} &nbsp;|&nbsp; ✗ {hyp.get('evidence_against','')}
                        </div>
                    </div>""",
                    unsafe_allow_html=True,
                )
        elif plan.get("hypothesis"):
            st.markdown("#### 💡 Hypothesis")
            st.markdown(f'<div class="hypothesis">{plan["hypothesis"]}</div>', unsafe_allow_html=True)

        if plan.get("counter_arguments"):
            with st.expander("⚔️ Counter-arguments — strongest case against this idea"):
                for ca in plan["counter_arguments"]:
                    st.markdown(f"- {ca}")

        if plan.get("second_order_effects"):
            with st.expander("🌊 Second-order effects"):
                for eff in plan["second_order_effects"]:
                    st.markdown(f"- {eff}")

        if plan.get("riskiest_assumption"):
            st.markdown("#### ⚠️ Riskiest Assumption")
            st.warning(plan["riskiest_assumption"])
        if plan.get("cheapest_validation"):
            st.info(f"💡 **Cheapest validation:** {plan['cheapest_validation']}")

    # ── Tab 2: Interviews ────────────────────────────────────────────
    with tab_interviews:
        st.markdown("#### 👥 Who to Talk To")
        participants = plan.get("participants", [])
        for p in participants:
            access     = p.get("access", "Medium")
            color      = {"Easy": "green", "Medium": "orange", "Hard": "red", "Very Hard": "red"}.get(access, "grey")
            known_html = '<span class="known-badge">⭐ Known contact</span>' if p.get("known") else ""
            st.markdown(
                f"**{p.get('role','')}** &nbsp; :{color}[{access} access] &nbsp; "
                f"*{p.get('count','')} interviews* {known_html}",
                unsafe_allow_html=True,
            )
            if p.get("note"):
                st.caption(p["note"])

        if plan.get("participant_notes"):
            st.info(plan["participant_notes"])

        st.divider()
        st.markdown("#### ❓ Interview Questions")
        iqs = plan.get("interview_questions", [])
        for i, iq in enumerate(iqs, 1):
            intent = iq.get("intent", "")
            st.markdown(
                f"**Q{i}.** {iq['question']} <span class='iq-intent'>{intent}</span>",
                unsafe_allow_html=True,
            )
            if iq.get("intent_desc"):
                st.caption(f"*{iq['intent_desc']}*")
            st.markdown("")

    # ── Tab 3: Data & Evidence ───────────────────────────────────────
    with tab_data:
        st.markdown("#### 📊 Data Signals to Pull")
        signals = plan.get("data_signals", [])
        for sig in signals:
            conf_label  = f" · **{sig['signal_confidence'].upper()}** signal" if sig.get("signal_confidence") else ""
            inj_html    = '<span class="injected-badge">🔗 Your system</span>' if sig.get("injected") else ""
            st.markdown(
                f"**{sig['metric']}** `{sig.get('source','')}` {conf_label} {inj_html}",
                unsafe_allow_html=True,
            )
            st.caption(sig.get("description", ""))

        st.divider()
        st.markdown("#### ✅ Success Criteria")
        st.caption("Check off as you research. **Minimum 2** required to unlock the Idea Card.")
        criteria = plan.get("success_criteria", [])
        if len(st.session_state.checked_criteria) != len(criteria):
            st.session_state.checked_criteria = [False] * len(criteria)

        for i, sc in enumerate(criteria):
            type_icon = {"Confirmed": "🟢", "Quantified": "🔵", "Disproved": "🟠", "Blocker": "🔴"}.get(sc.get("type", ""), "⚪")
            st.session_state.checked_criteria[i] = st.checkbox(
                f"{type_icon} **{sc.get('type','')}** — {sc['criterion']}",
                value=st.session_state.checked_criteria[i],
                key=f"crit_{i}",
            )

        checked = sum(1 for c in st.session_state.checked_criteria if c)
        st.progress(min(checked / 2, 1.0), text=f"{checked}/2 criteria checked")

    # ── Tab 4: Methods ───────────────────────────────────────────────
    with tab_methods:
        st.markdown("#### 🧪 Research Methods")
        methods = plan.get("research_methods", [])
        cols    = st.columns(len(methods)) if methods else [st]
        for i, m in enumerate(methods):
            col   = cols[i] if i < len(cols) else cols[0]
            prio  = m.get("priority", "")
            badge = "🟣 Primary" if prio == "Primary" else ("🔵 Secondary" if prio == "Secondary" else "🟢 Validation")
            col.markdown(f"**{badge}**")
            col.markdown(f"**{m['method']}**")
            col.caption(m.get("rationale", ""))
            col.markdown(f"*Target: {m.get('count', '')}*")

        if plan.get("timeline_guidance"):
            st.info(f"🗓️ {plan['timeline_guidance']}")

    # ---- Navigation (outside tabs, always visible) ----
    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        if st.button("← Back to Verdict", use_container_width=True):
            go("verdict")
    with col2:
        if st.button("Log Research Findings →", type="primary", use_container_width=True):
            go("findings")

# ------------------------------------------------------------------ #
# SCREEN: Research Findings
# ------------------------------------------------------------------ #


# ------------------------------------------------------------------ #
# SCREEN: Research Findings (Phase 5: Action Tracker)
# ------------------------------------------------------------------ #

def screen_findings():
    """Research findings + Phase 5 Action Tracker."""
    st.markdown("## 📝 Log Research Findings")
    st.caption("Log what you learned. Minimum 1 finding unlocks the Idea Card.")

    for i in range(5):
        st.session_state.findings[i] = st.text_area(
            f"Finding {i+1}",
            value=st.session_state.findings[i],
            placeholder="e.g. 4 of 5 interviewees confirmed this problem occurs daily and takes 2+ hrs each time.",
            height=68,
            key=f"finding_{i}",
        )

    st.markdown("### 💡 Proposed Direction (optional)")
    st.session_state.proposed_direction = st.text_area(
        "What solution direction does your research point to?",
        value=st.session_state.proposed_direction,
        placeholder="e.g. An automated matching layer above SAP that routes exceptions to the right approver.",
        height=80,
    )

    # ── Phase 5: Research Plan Action Tracker ────────────────────────
    _plan       = st.session_state.get("research_plan") or {}
    _verdict    = st.session_state.get("verdict")
    _idea_title = st.session_state.idea_title
    _tracker    = ActionTracker()

    with st.expander("🗂️ Research Action Tracker", expanded=True):
        if not st.session_state.actions_seeded and _plan and _verdict:
            import uuid as _uuid
            _seeded = ActionTracker.scaffold_from_plan(
                idea_title=_idea_title,
                research_plan=_plan,
                verdict_next_steps=_verdict.next_steps if _verdict else [],
            )
            for _item in _seeded:
                _tracker.add(_item)
            st.session_state.actions_seeded = True

        _actions = _tracker.get_for_idea(_idea_title)
        _summary = _tracker.summary_for_idea(_idea_title)

        if _summary["total"] > 0:
            st.progress(_summary["pct_done"] / 100,
                        text=f"{_summary['done']}/{_summary['total']} actions done ({_summary['pct_done']}%)")
            if _summary.get("overdue", 0):
                st.warning(f"⚠️ {_summary['overdue']} overdue action(s)")

        for _action in _actions:
            _ac1, _ac2, _ac3 = st.columns([5, 2, 1])
            with _ac1:
                _done_icon = "✅" if _action.is_done else _action.priority_icon
                st.markdown(
                    f"{_done_icon} **{_action.title}** "
                    f'<span style="font-size:11px;color:#94a3b8">{_action.source_label}</span>',
                    unsafe_allow_html=True,
                )
            with _ac2:
                _new_status = st.selectbox(
                    "Status", ACTION_STATUSES,
                    index=ACTION_STATUSES.index(_action.status) if _action.status in ACTION_STATUSES else 0,
                    key=f"act_status_{_action.id}",
                    label_visibility="collapsed",
                )
                if _new_status != _action.status:
                    _tracker.update_status(_action.id, _new_status)
                    st.rerun()
            with _ac3:
                if st.button("🗑️", key=f"del_act_{_action.id}", help="Remove"):
                    _tracker.delete(_action.id)
                    st.rerun()

        with st.form(key="add_action_form", clear_on_submit=True):
            _new_title    = st.text_input("Add a custom action",
                                          placeholder="e.g. Schedule interview with SC planners")
            _new_priority = st.selectbox("Priority", ["High", "Medium", "Low"], index=1)
            if st.form_submit_button("➕ Add"):
                if _new_title.strip():
                    import uuid as _uuid2
                    _tracker.add(ActionItem(
                        id=str(_uuid2.uuid4())[:8],
                        idea_title=_idea_title,
                        title=_new_title.strip(),
                        source="manual",
                        priority=_new_priority,
                    ))
                    st.rerun()

    generator = IdeaCardGenerator()
    can_generate, gate_msg = generator.check_gate(
        st.session_state.checked_criteria,
        st.session_state.findings,
    )
    if can_generate:
        st.success(f"✅ {gate_msg}")
    else:
        st.warning(f"🔒 {gate_msg}")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("← Back to Research Plan", use_container_width=True):
            go("research_plan")
    with col2:
        if st.button("Generate Idea Card →", type="primary",
                     disabled=not can_generate, use_container_width=True):
            go("idea_card")


# ------------------------------------------------------------------ #
# SCREEN: Idea Card (Phase 4 & 5: BRM, DMAIC, Integrations, Team)
# ------------------------------------------------------------------ #

def screen_idea_card():
    """Idea Card with tabbed Phase 4 & 5 panels."""
    verdict   = st.session_state.verdict
    engine    = st.session_state.engine
    plan      = st.session_state.research_plan or {}
    generator = IdeaCardGenerator()

    card = generator.generate(
        answers=engine.answers,
        verdict=verdict,
        idea_title=st.session_state.idea_title,
        idea_description=st.session_state.idea_description,
        research_plan=plan,
        findings=[f for f in st.session_state.findings if f.strip()],
        proposed_direction=st.session_state.proposed_direction,
    )
    st.session_state.idea_card = card
    card_dict = card.to_dict()

    st.markdown("## 🃏 Idea Card")
    st.markdown(
        f'''<div class="idea-card-header">
            <div style="display:flex;justify-content:space-between;align-items:flex-start">
                <div>
                    <div style="font-size:18px;font-weight:700;margin-bottom:4px">{card.title}</div>
                    <div style="font-size:12px;opacity:0.8">{card.domain} · {card.origin} · {card.date_created}</div>
                </div>
                <div style="text-align:center;background:white;color:#6366f1;font-weight:800;
                           font-size:22px;padding:6px 14px;border-radius:20px;white-space:nowrap">
                    {card.verdict_emoji} {int(card.verdict_score)}
                </div>
            </div>
            <div style="font-size:13px;margin-top:10px;opacity:0.9">{card.description}</div>
        </div>''',
        unsafe_allow_html=True,
    )

    tab_card, tab_brm, tab_dmaic, tab_int, tab_team = st.tabs([
        "🃏 Idea Card", "📈 BRM Outcomes", "📐 DMAIC", "🔗 Integrations", "👥 Team"
    ])

    # ── Tab 1: Idea Card ───────────────────────────────────────────────
    with tab_card:
        st.markdown('<div class="idea-card-body">', unsafe_allow_html=True)
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Problem Statement**"); st.markdown(card.problem)
            st.markdown("**Current State**");     st.markdown(card.current_state)
        with col2:
            st.markdown("**Primary User**");         st.markdown(card.primary_stakeholder)
            st.markdown("**Proposed Direction**");    st.markdown(card.proposed_direction or "*(not yet defined)*")
        st.divider()
        st.markdown("**Hypothesis**")
        st.markdown(f'<div class="hypothesis">{card.hypothesis}</div>', unsafe_allow_html=True)
        st.divider()
        col3, col4 = st.columns(2)
        with col3:
            st.markdown("**Validated Evidence**")
            if card.validated_evidence:
                for e in card.validated_evidence: st.markdown(f"- {e}")
            else: st.caption("*(no findings logged yet)*")
        with col4:
            st.markdown("**Key Adoption Risk**"); st.markdown(card.key_adoption_risk)
        st.divider()
        st.markdown("**Open Questions**")
        for oq in card.open_questions:
            if oq.strip(): st.markdown(f"- {oq}")
        st.markdown("**Next Actions**")
        for na in card.next_actions: st.markdown(f"- ☐ {na}")
        for flag in card.confidence_flags:
            if flag: st.warning(flag)
        st.markdown('</div>', unsafe_allow_html=True)
        st.divider()
        ca, cb, cc = st.columns(3)
        with ca:
            st.download_button("📄 Export Markdown", data=card.to_markdown(),
                file_name=f"skout_{card.title[:30].replace(' ','_')}.md", mime="text/markdown",
                use_container_width=True)
        with cb:
            st.download_button("📦 Export JSON", data=json.dumps(card_dict, indent=2),
                file_name=f"skout_{card.title[:30].replace(' ','_')}.json", mime="application/json",
                use_container_width=True)
        with cc:
            if st.button("🔄 Start New Idea", use_container_width=True):
                for key in ["verdict","research_plan","findings","checked_criteria","proposed_direction",
                            "idea_card","idea_title","idea_description","idea_recorded",
                            "signal","dmaic_canvas","actions_seeded"]:
                    st.session_state.pop(key, None)
                st.session_state.engine.reset()
                init_state()
                go("idea_input")

    # ── Tab 2: BRM Outcomes ───────────────────────────────────────────
    with tab_brm:
        st.markdown("### 📈 Benefits Realisation Management")
        _brm    = BRMTracker()
        _record = _brm.get_by_title(card.title) or BRMTracker.scaffold_from_card(
            card.title, card.domain, card.verdict_score, card.next_actions)

        bc1, bc2, bc3 = st.columns(3)
        with bc1:
            _ns = st.selectbox("Status", REALISATION_STATUS,
                index=REALISATION_STATUS.index(_record.status) if _record.status in REALISATION_STATUS else 0,
                key="brm_status")
            _record.status = _ns
        with bc2:
            _record.go_live_date = st.text_input("Go-live (YYYY-MM-DD)", value=_record.go_live_date or "", key="brm_gl")
        with bc3:
            _record.review_date  = st.text_input("Next review (YYYY-MM-DD)", value=_record.review_date or "", key="brm_rv")

        st.divider()
        st.markdown("#### 💰 Benefits")
        if not _record.benefits:
            _record.benefits = [BenefitItem(BENEFIT_CATEGORIES[0], "", 0.0, "%")]

        for _idx, _ben in enumerate(_record.benefits):
            with st.expander(f"Benefit {_idx+1}: {_ben.category}", expanded=_idx == 0):
                _bb1, _bb2 = st.columns(2)
                with _bb1:
                    _ben.category = st.selectbox("Category", BENEFIT_CATEGORIES,
                        index=BENEFIT_CATEGORIES.index(_ben.category) if _ben.category in BENEFIT_CATEGORIES else 0,
                        key=f"bc_{_idx}")
                    _ben.description = st.text_input("Description", value=_ben.description,
                        key=f"bd_{_idx}", placeholder="e.g. Reduce exception rate")
                with _bb2:
                    _pv, _pu = st.columns(2)
                    with _pv: _ben.predicted_value = st.number_input("Predicted", value=float(_ben.predicted_value), key=f"bpv_{_idx}", min_value=0.0)
                    with _pu: _ben.predicted_unit = st.selectbox("Unit", MEASUREMENT_UNITS,
                        index=MEASUREMENT_UNITS.index(_ben.predicted_unit) if _ben.predicted_unit in MEASUREMENT_UNITS else 0,
                        key=f"bpu_{_idx}")
                    _av, _au = st.columns(2)
                    with _av:
                        _ar = st.number_input("Actual", value=float(_ben.actual_value or 0), key=f"bav_{_idx}", min_value=0.0)
                        _ben.actual_value = _ar if _ar > 0 else None
                    with _au: _ben.actual_unit = st.selectbox("Unit ", MEASUREMENT_UNITS,
                        index=MEASUREMENT_UNITS.index(_ben.actual_unit) if _ben.actual_unit in MEASUREMENT_UNITS else 0,
                        key=f"bau_{_idx}")
                if _ben.realisation_pct is not None:
                    _pc = _ben.realisation_pct
                    _col = "#16a34a" if _pc >= 90 else ("#ca8a04" if _pc >= 60 else "#dc2626")
                    st.markdown(f'<span style="color:{_col};font-weight:700">Realisation: {_pc}%</span>', unsafe_allow_html=True)

        _ba1, _ba2 = st.columns(2)
        with _ba1:
            if st.button("➕ Add benefit", key="brm_add"):
                _record.benefits.append(BenefitItem(BENEFIT_CATEGORIES[0], "", 0.0, "%")); st.rerun()
        with _ba2:
            if _record.benefits and st.button("🗑️ Remove last", key="brm_rm"):
                _record.benefits.pop(); st.rerun()

        st.divider()
        st.markdown("#### 🏁 Milestones")
        for _mi, _ms in enumerate(_record.milestones):
            _mc1, _mc2, _mc3 = st.columns([5, 2, 1])
            _ms_icon = '✅' if _ms.get('done') else '⬜'
            with _mc1: st.markdown(f"{_ms_icon} **{_ms['name']}** · due {_ms.get('due','TBD')}")
            with _mc2:
                if not _ms.get("done"):
                    if st.button("Mark done", key=f"ms_{_mi}"):
                        from datetime import date as _d
                        _record.milestones[_mi].update({"done": True, "date_done": _d.today().isoformat()})
                        _brm.upsert(_record); st.rerun()
            with _mc3:
                if st.button("🗑️", key=f"msd_{_mi}"):
                    _record.milestones.pop(_mi); _brm.upsert(_record); st.rerun()

        with st.form("ms_form", clear_on_submit=True):
            _mn = st.text_input("Milestone", placeholder="e.g. Complete stakeholder interviews")
            _md = st.text_input("Due (YYYY-MM-DD)", placeholder="2026-07-01")
            if st.form_submit_button("➕ Add milestone"):
                if _mn.strip():
                    _record.milestones.append({"name": _mn.strip(), "due": _md.strip(), "done": False, "date_done": None})
                    _brm.upsert(_record); st.rerun()

        _record.lessons_learned      = st.text_area("Lessons learned",      value=_record.lessons_learned,      height=70, key="brm_ll")
        _record.stakeholder_feedback = st.text_area("Stakeholder feedback",  value=_record.stakeholder_feedback,  height=60, key="brm_sf")

        if st.button("💾 Save BRM Record", type="primary"):
            _brm.upsert(_record); st.success("✅ BRM record saved.")

        _ps = _brm.portfolio_summary()
        if _ps.get("total", 0) > 1:
            st.divider(); st.markdown("#### 📊 Portfolio")
            _p1, _p2, _p3 = st.columns(3)
            _p1.metric("Tracked", _ps["total"]); _p2.metric("Delivered", _ps.get("delivered_count", 0))
            if _ps.get("avg_realisation"): _p3.metric("Avg realisation", f"{_ps['avg_realisation']}%")

    # ── Tab 3: DMAIC ──────────────────────────────────────────────────
    with tab_dmaic:
        st.markdown("### 📐 DMAIC Canvas")
        _dmaic = st.session_state.get("dmaic_canvas")
        if _dmaic is None:
            st.info("Build the DMAIC canvas from the Verdict screen, or generate it now.")
            if st.button("🔨 Build DMAIC Canvas", key="dmaic_card"):
                _dmaic = DMAICEngine().build(
                    answers=engine.answers, idea_title=card.title,
                    idea_description=card.description, research_plan=plan,
                    verdict_score=card.verdict_score)
                st.session_state.dmaic_canvas = _dmaic; st.rerun()
        else:
            _d_t, _m_t, _a_t, _i_t, _c_t = st.tabs(["D—Define","M—Measure","A—Analyze","I—Improve","C—Control"])
            with _d_t:
                for _lbl, _val in [("Problem Statement", _dmaic.problem_statement),
                                   ("Scope", _dmaic.project_scope),
                                   ("Voice of Customer", _dmaic.voice_of_customer),
                                   ("Goal Statement", _dmaic.goal_statement)]:
                    st.markdown(f"##### {_lbl}"); st.markdown(_val)
                st.markdown("##### SIPOC")
                for _k in ["suppliers","inputs","process","outputs","customers"]:
                    _v = _dmaic.sipoc.get(_k, [])
                    st.markdown(f"**{_k.title()}:** " + (", ".join(_v) if isinstance(_v, list) else str(_v)))
            with _m_t:
                st.markdown("##### Baseline Metrics")
                for _bm in _dmaic.baseline_metrics: st.markdown(f"- {_bm}")
                st.markdown("##### Measurement Plan"); st.markdown(_dmaic.measurement_plan)
            with _a_t:
                st.markdown("##### Root Cause Categories (Fishbone)")
                for _cat in _dmaic.root_cause_categories:
                    with st.expander(_cat):
                        _hyp = st.text_area("Hypothesis", value=_dmaic.fishbone_branches.get(_cat,""),
                                            key=f"fish_{_cat[:15]}", height=60)
                        _dmaic.fishbone_branches[_cat] = _hyp
                if _dmaic.riskiest_assumption:
                    st.warning(f"⚠️ Riskiest assumption: {_dmaic.riskiest_assumption}")
            with _i_t:
                st.markdown("##### Solution Direction"); st.markdown(_dmaic.solution_direction)
                st.markdown("##### Quick Wins")
                for _qw in _dmaic.quick_wins: st.markdown(f"- {_qw}")
                st.markdown("##### Strategic Changes")
                for _sc in _dmaic.strategic_changes: st.markdown(f"- {_sc}")
            with _c_t:
                st.markdown("##### Success Criteria")
                for _sc in _dmaic.success_criteria:
                    _icon = {"Confirmed":"🟢","Quantified":"🔵","Disproved":"🟠","Blocker":"🔴"}.get(_sc.get("type",""),"⚪")
                    st.markdown(f"- {_icon} **{_sc.get('type','')}** — {_sc.get('criterion','')}")
                st.markdown("##### Control Plan"); st.markdown(_dmaic.control_plan)
            st.divider()
            st.download_button("📄 Download DMAIC (.md)", data=_dmaic.to_markdown(),
                file_name=f"dmaic_{card.title[:25].replace(' ','_')}.md", mime="text/markdown",
                use_container_width=True)

    # ── Tab 4: Integrations ───────────────────────────────────────────
    with tab_int:
        st.markdown("### 🔗 Export & Integrations")
        _n_t, _j_t, _w_t, _c_t = st.tabs(["Notion", "Jira", "Webhook", "CSV"])

        with _n_t:
            st.markdown("#### 📝 Notion Markdown Export")
            _notion_md = to_notion_markdown(card_dict)
            st.text_area("Notion markdown", value=_notion_md, height=280, key="notion_ta")
            st.download_button("📥 Download Notion (.md)", data=_notion_md,
                file_name=f"notion_{card.title[:25].replace(' ','_')}.md", mime="text/markdown",
                use_container_width=True)

        with _j_t:
            st.markdown("#### 🟦 Jira Issue Export")
            _pk = st.text_input("Jira project key", value="SC", max_chars=10)
            _jira_json = to_jira_json_str(card_dict, _pk)
            st.code(_jira_json, language="json")
            st.download_button("📥 Download Jira JSON", data=_jira_json,
                file_name=f"jira_{card.title[:25].replace(' ','_')}.json", mime="application/json",
                use_container_width=True)
            st.caption("POST to: `POST /rest/api/3/issue`")

        with _w_t:
            st.markdown("#### 🌐 Webhook POST")
            _wurl = st.text_input("Webhook URL", value=st.session_state.get("webhook_url",""),
                placeholder="https://hooks.zapier.com/hooks/catch/…", key="wh_url_input")
            st.session_state.webhook_url = _wurl
            _extra_raw = st.text_input("Extra metadata (key=value)", placeholder="source=skout,env=prod")
            _extra = {}
            for _p in _extra_raw.split(","):
                if "=" in _p:
                    _k, _v = _p.split("=", 1)
                    _extra[_k.strip()] = _v.strip()
            if st.button("🚀 Send to Webhook", type="primary", disabled=not _wurl.strip()):
                _payload = build_webhook_payload(card_dict, _extra or None)
                with st.spinner("Sending…"):
                    _res = post_webhook(_wurl.strip(), _payload)
                if _res.success:
                    st.success(f"✅ Delivered — HTTP {_res.status_code}")
                else:
                    st.error(f"❌ Failed: {_res.error or _res.status_code}")
            with st.expander("Preview payload"):
                st.code(json.dumps(build_webhook_payload(card_dict), indent=2), language="json")

        with _c_t:
            st.markdown("#### 📊 CSV Export")
            st.download_button("📥 Download CSV", data=to_csv([card_dict]),
                file_name=f"skout_{card.title[:20].replace(' ','_')}.csv", mime="text/csv",
                use_container_width=True)

    # ── Tab 5: Team Mode ──────────────────────────────────────────────
    with tab_team:
        st.markdown("### 👥 Team Mode — Shared Idea Pool")
        _ucm     = st.session_state.get("ucm")
        _profile = _ucm.get_profile() if _ucm else {}
        _author  = (_profile.get("name") or "Anonymous") if _profile else "Anonymous"
        _tid     = st.session_state.get("team_id", "default")
        _tc1, _tc2 = st.columns([3, 1])
        with _tc1:
            _tid_in = st.text_input("Team ID", value=_tid, placeholder="e.g. sc-product-team",
                help="Anyone sharing the same Team ID can see shared ideas.")
        with _tc2:
            if st.button("Apply", key="apply_tid"):
                st.session_state.team_id = _tid_in.strip() or "default"; st.rerun()
        _tid = st.session_state.get("team_id", "default")

        if st.button("📤 Share this idea to team pool", type="primary"):
            _shared = share_to_team(card_dict, author=_author, team_id=_tid)
            if _shared: st.success(f"✅ Shared to team '{_tid}'!")
            else: st.info("This idea is already in the team pool.")

        st.divider()
        st.markdown("#### 🗂️ Shared Ideas")
        _team_ideas = get_team_ideas(_tid)
        if not _team_ideas:
            st.caption("No ideas shared yet. Share one above!")
        else:
            for _ti in reversed(_team_ideas):
                _icon = "🟢" if _ti.get("score",0) >= 80 else "🟡"
                with st.expander(f"{_icon} {_ti['title']} — {int(_ti.get('score',0))}/100 · {_ti.get('author','')} · {_ti.get('shared_date','')}"):
                    st.markdown(f"**Domain:** {_ti.get('domain','')} · **Band:** {_ti.get('band','')}")
                    if _ti.get("hypothesis"): st.markdown(f"*{_ti['hypothesis'][:200]}…*")
                    if _ti.get("next_actions"): st.markdown("**Actions:** " + " · ".join(_ti["next_actions"][:3]))
                    for _c in _ti.get("comments", []):
                        st.markdown(f"💬 **{_c['author']}** ({_c['date']}): {_c['text']}")
                    with st.form(key=f"cmt_{_ti['title'][:15]}"):
                        _ctxt = st.text_input("Add comment", key=f"c_{_ti['title'][:12]}")
                        if st.form_submit_button("Send"):
                            if _ctxt.strip(): add_team_comment(_ti["title"], _author, _ctxt.strip(), _tid); st.rerun()



# ------------------------------------------------------------------ #
# SCREEN: All Ideas History
# ------------------------------------------------------------------ #

def screen_history():
    """
    SCREEN: All Ideas — full history list with load buttons.
    """
    st.markdown("## 📂 All Ideas")
    ucm = st.session_state.get("ucm")
    if not ucm:
        st.info("No history yet — evaluate an idea to get started.")
        if st.button("← Back", use_container_width=False):
            go("idea_input")
        return

    all_ideas = ucm.get_ideas_history()
    if not all_ideas:
        st.info("No ideas evaluated yet.")
        if st.button("← Evaluate your first idea", type="primary"):
            go("idea_input")
        return

    band_meta = {
        "high_priority": ("🟢", "#f0fdf4", "#15803d", "#86efac", "GO"),
        "promising":     ("🟡", "#fefce8", "#b45309", "#fbbf24", "REFINE"),
        "needs_clarity": ("🟠", "#fff7ed", "#c2410c", "#fb923c", "REFINE"),
        "not_ready":     ("🔴", "#fef2f2", "#b91c1c", "#fca5a5", "STOP"),
    }

    # ── Summary stats row ─────────────────────────────────────────
    total      = len(all_ideas)
    go_count   = sum(1 for i in all_ideas if i.get("verdict", {}).get("band") == "high_priority")
    avg_score  = int(sum(i.get("score", 0) for i in all_ideas) / total) if total else 0
    top_domain = ""
    from collections import Counter
    domain_counts = Counter(i.get("domain", "") for i in all_ideas if i.get("domain"))
    if domain_counts:
        top_domain = domain_counts.most_common(1)[0][0].replace("_", " ").title()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total ideas", total)
    c2.metric("GO decisions", go_count)
    c3.metric("Avg score", f"{avg_score}/100")
    c4.metric("Top domain", top_domain or "—")

    st.divider()

    # ── Filter row ────────────────────────────────────────────────
    _fcol1, _fcol2 = st.columns([2, 3])
    with _fcol1:
        _filter_band = st.selectbox(
            "Filter by decision",
            ["All", "🟢 GO", "🟡 REFINE (promising)", "🟠 REFINE (needs clarity)", "🔴 STOP"],
            key="hist_filter_band",
        )
    with _fcol2:
        _search = st.text_input("Search by title", placeholder="Type to filter…", key="hist_search")

    band_filter_map = {
        "🟢 GO":                   "high_priority",
        "🟡 REFINE (promising)":   "promising",
        "🟠 REFINE (needs clarity)": "needs_clarity",
        "🔴 STOP":                 "not_ready",
    }
    _band_key = band_filter_map.get(_filter_band, None)

    filtered = [
        (idx, idea) for idx, idea in enumerate(all_ideas)
        if (_band_key is None or idea.get("verdict", {}).get("band") == _band_key)
        and (_search.strip() == "" or _search.strip().lower() in (idea.get("title") or "").lower())
    ]

    if not filtered:
        st.info("No ideas match the current filter.")
    else:
        st.caption(f"Showing {len(filtered)} of {total} ideas")
        for _idx, idea in filtered:
            _band   = idea.get("verdict", {}).get("band", "")
            _emoji, _bg, _fg, _border, _dec = band_meta.get(
                _band, ("⚪", "#f8fafc", "#374151", "#e2e8f0", "—")
            )
            _score   = int(idea.get("score", 0))
            _title   = idea.get("title", "Untitled")
            _domain  = idea.get("domain", "").replace("_", " ").title()
            _date    = idea.get("date", "")
            _outcome = idea.get("outcome", "") or ""

            _ca, _cb = st.columns([5, 1])
            with _ca:
                st.markdown(
                    f'<div style="background:{_bg};border:1px solid {_border};border-radius:8px;'
                    f'padding:10px 14px;margin-bottom:4px">'
                    f'<div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">'
                    f'<span style="font-size:16px">{_emoji}</span>'
                    f'<span style="font-size:14px;font-weight:600;color:#0f172a">{_title}</span>'
                    f'<span style="font-size:12px;font-weight:700;color:{_fg}">{_score}/100 · {_dec}</span>'
                    f'<span style="font-size:11px;color:#64748b">{_domain}</span>'
                    f'<span style="font-size:11px;color:#94a3b8">{_date}</span>'
                    + (f'<span style="font-size:11px;background:#e0f2fe;color:#0369a1;'
                       f'padding:1px 6px;border-radius:3px">{_outcome}</span>' if _outcome else "")
                    + f'</div></div>',
                    unsafe_allow_html=True,
                )
            with _cb:
                if idea.get("verdict"):
                    if st.button("Load ↗", key=f"hs_load_{_idx}", use_container_width=True):
                        from core.scoring_engine import VerdictResult as _VR3
                        st.session_state.idea_title       = idea.get("title", "")
                        st.session_state.idea_description = ""
                        st.session_state.verdict          = _VR3.from_dict(idea["verdict"])
                        st.session_state.idea_recorded    = True
                        st.session_state.domain_audit     = None
                        st.session_state.research_plan    = None
                        st.session_state.dmaic_canvas     = None
                        st.session_state.idea_findings    = {}
                        if idea.get("answers"):
                            st.session_state.engine.answers = dict(idea["answers"])
                        go("verdict")
                else:
                    st.caption("—")

    st.divider()
    if st.button("← Back to home", use_container_width=False):
        go("idea_input")


# ------------------------------------------------------------------ #
# Sidebar
# ------------------------------------------------------------------ #

def render_sidebar():
    """Persistent sidebar with Phase 4/5 indicators."""
    with st.sidebar:
        st.markdown("### 🔭 Product Skout")

        ucm = st.session_state.get("ucm")
        if ucm and ucm.is_onboarded():
            profile = ucm.get_profile()
            name    = profile.get("name", "")
            role    = profile.get("role", "")
            org     = profile.get("organization", {})
            if name:  st.markdown(f"**{name}** · {role}")
            if org.get("type"): st.caption(f"{org.get('type')} · {org.get('size','')}")

            phase = ucm.get_phase()
            phase_colors = {0: "phase-0", 1: "phase-1", 2: "phase-2", 3: "phase-3"}
            st.markdown("---")
            st.markdown(
                f'<span class="phase-badge {phase_colors[phase]}">Phase {phase} — {ucm.phase_label()}</span>',
                unsafe_allow_html=True,
            )
            to_next = ucm.ideas_to_next_phase()
            if to_next > 0: st.caption(f"{to_next} idea(s) to Phase {phase + 1}")

            stats = ucm.get_stats()
            if stats["total"] > 0:
                c1, c2 = st.columns(2)
                c1.metric("Evaluated", stats["total"])
                c2.metric("High priority", stats["high_priority"])
                if stats.get("avg_score"):
                    st.caption(f"Avg: **{stats['avg_score']}** · Top: **{stats['top_domain']}**")


        if st.session_state.idea_title:
            st.markdown("---")
            st.markdown(f"**{st.session_state.idea_title}**")

        if st.session_state.step not in ("idea_input", "onboarding"):
            engine  = st.session_state.engine
            summary = engine.get_answered_summary()
            if summary:
                st.markdown("**Answers so far:**")
                for qid, label in [("origin","Source"),("q1","Domain"),("q2","Problem"),("q3","Stakeholder"),("q4","Today")]:
                    if qid in summary and isinstance(summary[qid], str):
                        st.caption(f"**{label}:** {summary[qid]}")
                if "q5" in summary and isinstance(summary["q5"], dict):
                    st.caption("**Impact:** rated ✓")

        if st.session_state.verdict:
            v = st.session_state.verdict
            st.markdown("---")
            st.markdown(f"**Verdict:** {v.band_emoji} {v.percent}/100")

        if ucm and ucm.get_phase() >= 1:
            history = ucm.get_ideas_history()
            if history:
                st.markdown("---")
                st.markdown("**Recent ideas**")
                for _hi, idea in enumerate(history[:5]):
                    score   = idea.get("score", 0)
                    title   = (idea.get("title") or "Untitled")
                    short   = title[:22] + "…" if len(title) > 22 else title
                    band    = idea.get("verdict", {}).get("band", "")
                    emoji   = {"high_priority": "🟢", "promising": "🟡",
                               "needs_clarity": "🟠", "not_ready": "🔴"}.get(band, "⚪")
                    _lc, _rc = st.columns([3, 1])
                    _lc.caption(f"{emoji} **{int(score)}** · {short}")
                    if idea.get("verdict") and _rc.button("↗", key=f"sb_load_{_hi}", help="Load this idea"):
                        from core.scoring_engine import VerdictResult as _VR
                        st.session_state.idea_title       = idea.get("title", "")
                        st.session_state.idea_description = ""
                        st.session_state.verdict          = _VR.from_dict(idea["verdict"])
                        st.session_state.idea_recorded    = True
                        st.session_state.domain_audit     = None
                        st.session_state.research_plan    = None
                        st.session_state.dmaic_canvas     = None
                        if idea.get("answers"):
                            st.session_state.engine.answers = dict(idea["answers"])
                        go("verdict")

        if ucm and ucm.is_onboarded():
            st.markdown("---")
            _sb1, _sb2 = st.columns(2)
            with _sb1:
                if st.button("✏️ Profile", use_container_width=True):
                    go("onboarding")
            with _sb2:
                if st.button("📂 All Ideas", use_container_width=True):
                    go("history")

        # ── Phase 4 & 5 indicators ──
        _sig = st.session_state.get("signal")
        if _sig:
            st.markdown("---")
            _ci = {"high": "🟢", "medium": "🟡", "low": "🔴"}.get(_sig.confidence, "⚪")
            st.caption(f"{_ci} Signal: `{_sig.source_type}` · domain: **{_sig.detected_domain}**")

        _tid = st.session_state.get("team_id", "default")
        _tm  = st.session_state.get("team_mode", False)
        st.markdown("---")
        _new_tm = st.checkbox("👥 Team Mode", value=_tm, key="sb_team")
        st.session_state.team_mode = _new_tm
        if _new_tm:
            st.caption(f"Pool: **{_tid}**")
            _ti = get_team_ideas(_tid)
            if _ti: st.caption(f"{len(_ti)} shared idea(s)")

        if st.session_state.get("dmaic_canvas"):
            st.markdown("---")
            st.caption("📐 DMAIC canvas ready")

        if st.session_state.idea_title:
            _at = ActionTracker()
            _as = _at.summary_for_idea(st.session_state.idea_title)
            if _as.get("total", 0) > 0:
                st.caption(f"🗂️ Actions: {_as['done']}/{_as['total']} done ({_as['pct_done']}%)")

        st.markdown("---")
        st.caption("v0.4 · Supply Chain Edition · Phase 4-5")


# ------------------------------------------------------------------ #
# Router
# ------------------------------------------------------------------ #

render_sidebar()

{
    "onboarding":    screen_onboarding,
    "idea_input":    screen_idea_input,
    "origin":        screen_origin,
    "q1":            screen_q1,
    "q2":            screen_q2,
    "q3":            screen_q3,
    "q4":            screen_q4,
    "q5":            screen_q5,
    "verdict":       screen_verdict,
    "research_plan": screen_research_plan,
    "findings":      screen_findings,
    "idea_card":     screen_idea_card,
    "history":       screen_history,
}.get(st.session_state.step, screen_idea_input)()
