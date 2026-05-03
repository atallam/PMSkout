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
                    "org_name": org_name.strip(), "org_type": org_type,
                    "org_size": org_size, "regions": regions,
                    "primary_domains": primary_domains,
                    "data_sources": data_sources,
                    "interview_count": interview_count,
                    "deep_think_threshold": deep_think_threshold,
                })
            st.success(f"Profile saved! Welcome, {name}.")
            go("idea_input")

    st.markdown("---")
    if st.button("Skip for now →"):
        ucm = st.session_state.get("ucm")
        if ucm:
            ucm.apply_onboarding({"name": "User", "role": "PM"})
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

    col1, col2 = st.columns([3, 1])
    with col2:
        if st.button("Start Evaluation →", type="primary", use_container_width=True):
            if not st.session_state.idea_title.strip():
                st.error("Give your idea a name to get started.")
            else:
                st.session_state.engine.reset()
                st.session_state.idea_recorded = False
                go("origin")

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
    SCREEN: Verdict
    Displays the score circle, band card, Stage-Gate recommendation, score breakdown
    (expandable), confidence flags, JTBD problem statement, McKinsey 3 Horizons
    classification, benchmark percentile, cost estimate, framework metrics
    (SCOR/WSJF/ODI), and the Domain Knowledge Audit section (7 patterns).
    Records the idea to ucm on first arrival. Unlocks Research Plan when score ≥ threshold.
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
        )
        st.session_state.idea_recorded = True
        for notif in ucm.get_unlock_notifications():
            st.toast(notif, icon="🔓")

    color = verdict.band_color

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

    # ── Stage-Gate Card (Phase 1) ──
    gate_text, gate_bg, gate_text_color, gate_border = _GATE_RECOMMENDATIONS.get(
        verdict.band,
        ("⚪ Gate 1: Evaluate Further", "#f8fafc", "#374151", "#cbd5e1"),
    )
    st.markdown(
        f"""<div class="gate-card" style="background:{gate_bg};border:1.5px solid {gate_border}">
            <div class="gate-dot" style="background:{gate_text_color}"></div>
            <div>
              <div class="gate-label" style="color:{gate_text_color}">{gate_text}</div>
              <div class="gate-sub" style="color:{gate_text_color}">Stage-Gate Model · Gate 1: Idea Screen</div>
            </div>
        </div>""",
        unsafe_allow_html=True,
    )

    # Score breakdown — expanded by default
    with st.expander("📊 Score breakdown", expanded=True):
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

    for flag in verdict.confidence_flags:
        ftype = flag.get("type", "info")
        css   = {"warning": "flag-warning", "info": "flag-info", "caution": "flag-caution"}.get(ftype, "flag-info")
        st.markdown(f'<div class="{css}">{flag["message"]}</div>', unsafe_allow_html=True)

    if verdict.next_steps:
        st.markdown("**Suggested next steps:**")
        for ns in verdict.next_steps:
            st.markdown(f"- {ns}")

    # ── JTBD Problem Statement (Phase 1) ──
    engine = st.session_state.engine
    if engine and engine.answers.get("q2"):
        jtbd = get_jtbd_statement(engine)
        st.markdown(
            f'<div class="jtbd-box">'
            f'<div class="jtbd-label">📌 JTBD Problem Statement</div>'
            f'{jtbd}'
            f'</div>',
            unsafe_allow_html=True,
        )

    # ── 3 Horizons Classification + Benchmark (Phase 1) ──
    q2 = engine.answers.get("q2", "") if engine else ""
    q4 = engine.answers.get("q4", "") if engine else ""
    if q2 or q4:
        h_code, h_label, h_bg, h_text_color, h_desc = get_horizon(verdict.band, q4, q2)

        col_h, col_b = st.columns([3, 2])
        with col_h:
            st.markdown(
                f'<div style="margin-bottom:6px">'
                f'<span style="font-size:11px;font-weight:700;color:#64748b;'
                f'text-transform:uppercase;letter-spacing:0.5px">McKinsey 3 Horizons</span>'
                f'</div>'
                f'<span class="horizon-pill" style="background:{h_bg};color:{h_text_color}">'
                f'{h_code} · {h_label}</span>'
                f'<div class="horizon-desc">{h_desc}</div>',
                unsafe_allow_html=True,
            )

        with col_b:
            ucm = st.session_state.get("ucm")
            domain = engine.answers.get("q1", "") if engine else ""
            bm = get_benchmark(ucm, domain, verdict.final_score)
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
            else:
                st.markdown(
                    '<div class="benchmark-row" style="color:#94a3b8">'
                    '<div style="font-size:11px;font-weight:700;text-transform:uppercase;'
                    'letter-spacing:0.5px;margin-bottom:4px">Benchmark</div>'
                    'Submit 2+ ideas to see percentile ranking.'
                    '</div>',
                    unsafe_allow_html=True,
                )

    # ── Cost estimate summary (if provided) ──
    cost_est = st.session_state.get("cost_estimate", "").strip()
    if cost_est:
        st.markdown(
            f'<div style="background:#fefce8;border:1px solid #fbbf24;border-radius:8px;'
            f'padding:10px 14px;font-size:13px;color:#713f12;margin-top:8px">'
            f'<strong>💰 Estimated cost impact:</strong> {cost_est}'
            f'</div>',
            unsafe_allow_html=True,
        )

    # ── Phase 2 — SCOR / WSJF / Opportunity Gap metrics strip ──
    with st.expander("📐 Framework Metrics", expanded=False):
        _scor  = verdict.scor_category
        _wsjf  = verdict.wsjf_score
        _opp   = verdict.opportunity_gap

        # SCOR alignment
        st.markdown(
            f'<div style="margin-bottom:10px">'
            f'<div style="font-size:11px;font-weight:700;color:#64748b;'
            f'text-transform:uppercase;letter-spacing:0.5px;margin-bottom:6px">SCOR Framework Alignment</div>'
            f'<span class="scor-pill">{verdict.scor_icon} {_scor}</span>'
            f'<div style="font-size:12px;color:#64748b;margin-top:5px">{verdict.scor_description}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        wsjf_color  = "#16a34a" if _wsjf >= 7 else ("#ca8a04" if _wsjf >= 4 else "#64748b")
        opp_color   = "#16a34a" if _opp  >= 14 else ("#ca8a04" if _opp  >= 8  else "#64748b")
        wsjf_band   = "High urgency" if _wsjf >= 7 else ("Moderate" if _wsjf >= 4 else "Low urgency")
        opp_band    = "Underserved" if _opp >= 14 else ("Moderate gap" if _opp >= 8 else "Well-served")

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
            "**WSJF** (Weighted Shortest Job First) = Cost of Delay ÷ Duration proxy — "
            "higher scores mean the delay cost outweighs the build effort. "
            "**Opportunity Gap** (Ulwick ODI) = Importance + max(Importance − Satisfaction, 0) — "
            "scores ≥14 indicate an underserved problem worth prioritising."
        )

    # ── Domain Knowledge Audit (7 Patterns) ──────────────────────────
    st.divider()
    st.markdown("### 🧠 Domain Knowledge Audit")
    st.caption(
        "Stress-tests your idea against 7 supply chain domain knowledge patterns: "
        "SCOR framework, challenger agent, KPI benchmarks, domain knowledge RAG, "
        "multi-dimensional scoring, and context sensitivity check."
    )

    # Context inputs (collapsible)
    with st.expander("⚙️ Audit context — set for more accurate results", expanded=False):
        col_a, col_b = st.columns(2)
        with col_a:
            industry = st.selectbox(
                "Industry vertical",
                ["default", "retail", "automotive", "pharma", "food_beverage", "electronics", "industrial"],
                key="audit_industry",
                help="Selects the right KPI benchmarks for your industry",
            )
            demand_pattern = st.selectbox(
                "Demand pattern",
                ["", "stable", "seasonal", "lumpy", "new_product", "event_driven"],
                key="audit_demand_pattern",
                help="Required for safety stock and inventory recommendations",
            )
        with col_b:
            maturity = st.selectbox(
                "Supply chain maturity",
                ["", "reactive", "defined", "optimised", "adaptive"],
                key="audit_maturity",
                help="Determines whether advanced analytics recommendations are realistic",
            )
            disruption = st.selectbox(
                "Disruption environment",
                ["", "stable", "elevated", "volatile", "crisis"],
                key="audit_disruption",
                help="Critical for lean/JIT and safety stock recommendations",
            )

    # Build context dict from selectors + existing Skout answers
    audit_ctx = {
        "industry":               st.session_state.get("audit_industry", "default"),
        "demand_pattern":         st.session_state.get("audit_demand_pattern", "") or None,
        "supply_chain_maturity":  st.session_state.get("audit_maturity", "") or None,
        "disruption_environment": st.session_state.get("audit_disruption", "") or None,
        "scor_domain":            st.session_state.engine.answers.get("q1", "") if st.session_state.engine else "",
    }

    if st.button("🔍 Run Domain Knowledge Audit", type="secondary", use_container_width=True):
        with st.spinner("Running 7 domain knowledge patterns…"):
            try:
                factory = st.session_state.get("factory")
                provider = factory.get_provider() if factory else None
                dk_engine = DomainKnowledgeEngine(
                    llm_provider=provider,
                    use_llm=True,
                    industry=audit_ctx.get("industry", "default"),
                )
                rec_text = (
                    st.session_state.get("idea_description", "")
                    or st.session_state.get("idea_title", "")
                )
                audit_result = dk_engine.evaluate(rec_text, audit_ctx)
                st.session_state.domain_audit = audit_result
                st.session_state.domain_audit_ctx = audit_ctx
            except Exception as e:
                st.error(f"Audit error: {e}")

    # Display audit results
    audit = st.session_state.get("domain_audit")
    if audit:
        # ── Overall verdict banner ──
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

        # ── Tabs for each pattern ──
        tab_ch, tab_kpi, tab_score, tab_ctx, tab_rag = st.tabs([
            f"⚔️ Challenges ({audit.challenger_summary.get('total',0)})",
            f"📊 KPI Warnings ({len(audit.kpi_warnings)})",
            "📐 Domain Score",
            "🌍 Context Check",
            "📚 Knowledge Retrieved",
        ])

        with tab_ch:
            # Pattern #1 — SCOR + Pattern #2 — Challenger
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

        with tab_kpi:
            # Pattern #3 — KPI Validator
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

        with tab_score:
            # Pattern #6 — Domain Scorer
            ds = audit.domain_score
            score_col1, score_col2 = st.columns([1, 2])
            with score_col1:
                sc_color = ds.verdict_color
                st.markdown(
                    f'<div style="background:{sc_color}18;border:2px solid {sc_color};border-radius:50%;'
                    f'width:110px;height:110px;display:flex;flex-direction:column;align-items:center;justify-content:center;margin:0 auto">'
                    f'<div style="font-size:28px;font-weight:800;color:{sc_color}">{ds.score_pct}%</div>'
                    f'<div style="font-size:11px;color:#6b7280">{ds.verdict}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            with score_col2:
                from core.domain_scorer import DIMENSION_LABELS
                for dim, label in DIMENSION_LABELS.items():
                    score_val = ds.dimension_scores.get(dim, 0.0)
                    # Normalise for display
                    if dim in ("cost_impact", "resilience_impact", "service_level_impact"):
                        bar_val = (score_val + 1.0) / 2.0
                        display = f"{score_val:+.2f}"
                        bar_color = "#16a34a" if score_val > 0.2 else ("#dc2626" if score_val < -0.2 else "#ca8a04")
                    else:
                        bar_val = score_val
                        display = f"{score_val:.2f}"
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

        with tab_ctx:
            # Pattern #7 — Context Checker
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

        with tab_rag:
            # Pattern #4 — RAG Store
            if not audit.rag_chunks:
                st.info("No domain knowledge chunks retrieved.")
            else:
                st.caption(f"Retrieved {len(audit.rag_chunks)} relevant knowledge chunks from the domain knowledge base:")
                for chunk in audit.rag_chunks:
                    cat_emoji = {"scor": "🏗️", "kpi": "📊", "failure_pattern": "⚠️"}.get(chunk.category, "📄")
                    relevance_pct = int(chunk.relevance * 100)
                    with st.expander(f"{cat_emoji} {chunk.source} — relevance {relevance_pct}%"):
                        st.markdown(f"```\n{chunk.content[:500]}\n```")

        # ── Action items ──
        if audit.action_items:
            st.markdown("**📋 Action items to address before proceeding:**")
            for i, item in enumerate(audit.action_items[:6], 1):
                st.markdown(f"{i}. {item}")


    # ── Phase 4: Ideas Like This ─────────────────────────────────────
    _engine  = st.session_state.engine
    _domain  = _engine.answers.get("q1", "")
    _problem = _engine.answers.get("q2", "")
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

    # ── Phase 4: DMAIC Mode ────────────────────────────────────────────
    with st.expander("📐 Frame as DMAIC problem", expanded=False):
        st.caption("Generate a Define / Measure / Analyze / Improve / Control canvas from your Q1–Q5 answers.")
        if st.button("🔨 Build DMAIC Canvas", key="build_dmaic"):
            _canvas = DMAICEngine().build(
                answers=st.session_state.engine.answers,
                idea_title=st.session_state.idea_title,
                idea_description=st.session_state.idea_description,
                research_plan=st.session_state.get("research_plan"),
                verdict_score=verdict.final_score,
            )
            st.session_state.dmaic_canvas = _canvas
            st.rerun()
        if st.session_state.get("dmaic_canvas"):
            st.success("✅ DMAIC canvas built — view it on the Idea Card screen.")
            st.download_button(
                "📄 Download DMAIC Canvas (.md)",
                data=st.session_state.dmaic_canvas.to_markdown(),
                file_name="dmaic_canvas.md",
                mime="text/markdown",
                use_container_width=True,
                key="dl_dmaic_verdict",
            )

    # ── Final navigation ──
    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        if st.button("← Reevaluate", use_container_width=True):
            st.session_state.engine.reset()
            go("idea_input")
    with col2:
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
                for idea in history[:5]:
                    score   = idea.get("score", 0)
                    title   = (idea.get("title") or "Untitled")
                    short   = title[:24] + "…" if len(title) > 24 else title
                    outcome = idea.get("outcome")
                    tag     = f" · {outcome}" if outcome else ""
                    st.caption(f"**{int(score)}** · {short}{tag}")

        if ucm and ucm.is_onboarded():
            st.markdown("---")
            if st.button("✏️ Edit Profile", use_container_width=True):
                go("onboarding")

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
}.get(st.session_state.step, screen_idea_input)()
