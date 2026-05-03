# Product Skout — Design Notes & Architecture Reference

> **Purpose:** This file captures the design assumptions, scoring logic, question rationale, and architectural decisions behind Product Skout. It is the single source of truth for anyone maintaining or extending the tool in the future.

---

## Table of Contents

1. [What Product Skout Does](#1-what-product-skout-does)
2. [Core Design Principles](#2-core-design-principles)
3. [Question Flow Design](#3-question-flow-design)
4. [Scoring Model](#4-scoring-model)
5. [Verdict Bands](#5-verdict-bands)
6. [Confidence Flags](#6-confidence-flags)
7. [Research Plan Generation](#7-research-plan-generation)
8. [Personalization & Phase System](#8-personalization--phase-system)
9. [Domain Coverage](#9-domain-coverage)
10. [Config File Map](#10-config-file-map)
11. [Key Architectural Decisions](#11-key-architectural-decisions)
12. [Known Limitations & Planned Improvements](#12-known-limitations--planned-improvements)

---

## 1. What Product Skout Does

Product Skout is a **supply chain idea evaluator**. It takes a product or feature idea and asks 5+1 structured questions to produce:

- A **verdict score** (0–100) with a band label and recommended action
- A **structured research plan** tailored to the domain and problem type
- A **shareable idea card** summarizing the idea for stakeholders

The tool is designed for product managers, solutions architects, and domain leads working in supply chain software. It replaces ad-hoc gut-feel evaluation with a consistent, repeatable signal.

---

## 2. Core Design Principles

**LLM-optional:** The scoring model is 100% rule-based. No LLM is required to get a verdict. LLMs (Claude by default) are only invoked for the optional research plan enrichment and extended thinking mode. The tool runs fully offline/on-premise if the LLM is disabled.

**Config-driven:** All questions, options, scores, weights, and thresholds live in YAML files — not hardcoded. This means the question set can be updated without touching Python code.

**Supply chain domain focus:** The questions and research templates are anchored in supply chain vocabulary (S&OP, MAPE, MTTR, PO cycle time, etc.). This specificity makes the output more actionable than a generic idea evaluator.

**Standalone deployment:** Designed to run locally with `streamlit run app.py`. No cloud dependency, no database server. State lives in YAML and JSON files on disk.

---

## 3. Question Flow Design

### Why 5 questions + 1 pre-question?

Research on effective idea evaluation (inspired by frameworks like RICE, ICE, and the Jobs-to-be-Done methodology) shows that five orthogonal dimensions capture most of the signal needed to triage a product idea. Fewer than five misses important dimensions; more than five increases cognitive load without adding proportional value.

The **pre-question (Origin)** is kept separate because it acts as a multiplier rather than a dimension score. It answers "how trustworthy is the signal behind this idea?" — which modulates the final score rather than contributing to a specific dimension.

### Pre-Question: Origin / Signal Source

**Question:** "Before we evaluate — where did this idea come from?"

**Why it matters:** The same idea framed as a leadership directive vs. a PM hypothesis should score differently because the evidence quality behind it differs. An idea with explicit user validation is more likely to be a real problem than an internal assumption.

**Multiplier logic:**

| Source | Multiplier | Rationale |
|--------|------------|-----------|
| Leadership request | ×1.35 | Strong strategic alignment signal; execs have visibility across the org |
| User / customer reported | ×1.30 | Direct problem evidence; highest confidence in real pain |
| Usage data / analytics | ×1.20 | Behavioral signal is objective; still needs interpretation |
| Partner or supplier feedback | ×1.10 | Ecosystem signal; slightly less direct than end-user pain |
| Internal PM hypothesis | ×1.00 | No external validation yet; neutral weight |
| Competitive signal | ×0.90 | Market intelligence needs user validation before committing |

**Design assumption:** Multiplier caps the final score at 100, so the boost for high-confidence sources cannot inflate a weak score above 100. The penalty for competitive signal (×0.90) reflects that "a competitor does X" is not sufficient justification to build X.

---

### Q1: Domain

**Scoring dimension:** `domain_fit` (max 10 points)

**Why domain fit is lowest weight:** Domain fit is a gating signal, not an impact driver. If the idea is in a supported domain, it scores fully (10/10). All supported domains currently score 10; the relative weighting reflects that knowing *what* domain the idea is in tells you less about prioritization than knowing *how bad* the problem is.

**Hidden domains:** Trade & Compliance and Fraud & Risk are present in `questions.yaml` with `hidden: true` and `wip: true`. They are invisible in the UI but fully preserved so the scoring engine, research planner, and Q2 branching logic don't need changes when they are activated. To re-enable: set `hidden: false` and `wip: false` in `questions.yaml`.

**Custom domains:** Users can define additional domains in `user_context.yaml` under `custom_extensions.domains`. These appear at the bottom of the Q1 list and use default scoring.

---

### Q2: Problem Type (Adaptive)

**Scoring dimension:** `problem_clarity` (max 25 points)

**Why adaptive:** The problem types relevant to "Procurement" are fundamentally different from those relevant to "Repair & MRO." A generic problem list would force users to map their domain-specific problem to an abstract category — introducing ambiguity and reducing scoring precision.

**Branching logic:** Q2 reads the Q1 answer and returns `domain_options[domain]`. If no domain match exists (e.g., custom domain), it falls back to `default_options`.

**Score spread across options:** Higher-specificity, higher-impact problems score higher. For example, "Supplier risk & visibility" (25 pts) scores higher than "Something else" (10 pts) in Procurement because the former signals a well-understood, high-stakes problem class while the latter is undefined.

---

### Q3: Affected Stakeholder

**Scoring dimension:** `stakeholder_reach` (max 15 points)

**Why:** The person experiencing the pain and the budget holder are often different. Surfacing this distinction helps PMs plan both discovery interviews (talk to the pain-feeler) and buy-in conversations (talk to the budget holder).

**Domain-aware reordering:** The option list reorders based on Q1 domain to surface the most relevant stakeholder first. The order is defined in `_Q3_DOMAIN_ORDER` in `question_engine.py`:

| Domain | Primary stakeholder |
|--------|-------------------|
| Planning | Supply Chain Planners |
| Procurement | Procurement / Category Mgrs |
| Repair | Operations / Field Teams |
| Trade | Finance & Compliance |
| Fraud | Finance & Compliance |

**Score rationale:**

| Stakeholder | Score | Rationale |
|------------|-------|-----------|
| Leadership / C-suite | 15 | Highest reach; they sponsor and fund solutions |
| SC Planners / Procurement Mgrs | 12 | Domain experts; direct users of supply chain tools |
| Operations / Finance | 10 | Broad but less tool-oriented |
| External Partners | 8 | Real pain, but harder to build for and sell to |

---

### Q4: Current State / Market Gap

**Scoring dimension:** `market_gap` (max 20 points)

**Why:** The best product ideas target problems with no adequate current solution — the "greenfield." An idea for a problem already served by a mature competitor is a harder market entry.

| Current state | Score | Rationale |
|--------------|-------|-----------|
| Manual / spreadsheets | 20 | Maximum greenfield signal |
| Not handled — ignored | 20 | Even higher signal: the problem isn't even acknowledged |
| Legacy ERP (SAP/Oracle) | 16 | System exists but fails; replacement opportunity |
| Multiple disconnected tools | 14 | Integration opportunity |
| Internal tool (not scalable) | 12 | Clear replacement candidate |
| Competitor product exists | 10 | Market exists; differentiation required |

---

### Q5: Business Impact (Multi-Factor)

**Scoring dimension:** `business_impact` (max 30 points = 3 factors × max 10 each)

**Why three sub-factors instead of one "impact" estimate:** A single "how big is this?" question is prone to optimism bias. Breaking it into three concrete, observable factors forces more honest answers:

- **Frequency** — How often does the problem occur? (Daily/weekly/monthly/rare)
- **Pain Severity** — What happens when it hits? (Work stops / major workaround / slows things / minor)
- **Workaround Cost** — What does the current fix actually cost? (>10 hrs/week / dedicated headcount / expensive tool / minimal)

Each factor scores 1, 4, 7, or 10. The three factors are additive. This approach is inspired by FMEA (Failure Mode and Effects Analysis) used in operations and engineering.

**Design decision:** Business Impact is the highest-weighted dimension (max 30/100) because it directly answers "is this worth building?" Domain fit (max 10) and stakeholder reach (max 15) are directional signals; business impact is the bottom-line question.

---

## 4. Scoring Model

### Dimension Weights

| Dimension | Question | Max Points | % of Total |
|-----------|----------|-----------|-----------|
| Business Impact | Q5 | 30 | 30% |
| Problem Clarity | Q2 | 25 | 25% |
| Market Gap | Q4 | 20 | 20% |
| Stakeholder Reach | Q3 | 15 | 15% |
| Domain Fit | Q1 | 10 | 10% |
| **Total base** | | **100** | **100%** |

### Origin Multiplier Application

```
final_score = min(100, base_score × origin_multiplier)
```

The multiplier can push a strong base score above 100 (capped), or gently discount an unvalidated idea. A perfect base score of 100 with a ×0.90 competitive signal multiplier becomes 90 — still high, but with a visible penalty signal.

### Custom Weight Override

Advanced users can override dimension weights in `user_context.yaml` under `scoring_customization.weights`. When `enabled: true`, the scoring engine normalizes user-supplied weights against the configured `max_points`. This allows organizations to tune the model for their priorities (e.g., a compliance-heavy org might weight `market_gap` lower since they often have no choice but to build certain features).

---

## 5. Verdict Bands

| Band | Score Range | Label | Action |
|------|------------|-------|--------|
| 🚀 | 80–100 | High Priority | Deep dive unlocked |
| 🔍 | 60–79 | Promising | Guided refinement |
| ⚠️ | 40–59 | Needs Clarity | Reevaluate prompt |
| ❌ | 0–39 | Not Ready | Reconsider scope |

**Deep Dive threshold:** Default is 80. Configurable in `user_context.yaml` under `research_preferences.deep_think_threshold`. When an idea meets the threshold, the full AI-powered research plan generation is unlocked.

**Design rationale for 80/60/40 thresholds:** These were calibrated to avoid grade inflation. With a balanced answer set, the "natural" mid-score is approximately 55–65. The 80 threshold for High Priority ensures only ideas with genuine multi-dimensional strength (high impact + clear problem + real market gap) qualify for deep research investment.

---

## 6. Confidence Flags

Flags appear on the verdict screen to add nuance the numeric score cannot capture:

**High Score, Low Validation** (warning): Fires when the origin is `pm_hypothesis` or `competitive_signal` AND the base score exceeds 70. Rationale: a PM hypothesis can score highly if the problem is internally well-understood, but without external validation it could be wrong. This flag prompts user research before committing resources.

**WIP Domain** (info): Fires when Q1 is `trade` or `fraud`. Signals that domain-specific branching is incomplete; the score is based on generic supply chain signals.

**Single Low Q5 Factor** (caution): Fires when any Q5 factor (frequency, severity, or workaround) scores 1 (minimum). A high total score with one very-low factor can mask a real weakness — e.g., a problem that's extremely severe but occurs only quarterly.

---

## 7. Research Plan Generation

### Three Modes

**Rule-based (no LLM):** Generates a fully structured research plan using predefined templates keyed by domain. Produces: hypothesis statement, 5 interview questions, participant profile, 4 data signals, and success criteria. Used as fallback when no LLM API key is configured.

**Standard LLM mode:** Uses the rule-based plan as a scaffold and asks the LLM to enrich it — sharper questions, more specific data pull instructions, hypothesis refinement. The LLM receives the full answers and scoring context.

**Deep Research mode (Ultrathink / Extended Thinking):** Unlocked when `final_score >= deep_think_threshold`. Uses Claude's extended thinking capability to generate competing hypotheses, counter-arguments, second-order effects, and a full validation roadmap. This is the highest-confidence output but takes longer and consumes more API tokens.

### User Context Injection

When Phase 1+ (`get_phase() >= 1`), the `UserContextManager.inject_into_plan()` method prepends the research plan with:
- Custom data sources from the user's configured systems (e.g., SAP S/4HANA, ServiceNow)
- Known domain stakeholders from the user's organization profile
- Previously validated ideas in the same domain (for comparison)

### Research Plan Tabs

The research plan UI is divided into four tabs to reduce vertical scrolling:

| Tab | Contents |
|-----|----------|
| Overview | Hypothesis, success criteria, plan-at-a-glance card |
| Interviews | Interview questions and participant profiles |
| Data & Evidence | Data signals, metrics, and sources |
| Methods | Research methods, timeline, and depth recommendation |

---

## 8. Personalization & Phase System

The `UserContextManager` tracks usage patterns and progressively unlocks features:

| Phase | Threshold | Unlocks |
|-------|-----------|---------|
| 0 — Onboarding | 0 ideas | Full onboarding wizard; no personalization yet |
| 1 — Learning | 1–5 ideas | Domain suggestion in Q1; similar-idea notices; sidebar stats |
| 2 — Adapting | 6–15 ideas | Scoring weight customization; custom data source injection in research plans |
| 3 — Personalising | 16+ ideas | Outcome tracking; cross-idea pattern alerts; historical trend view |

**Domain suggestion logic:** When Phase ≥ 1, `get_suggested_domain()` checks if ≥60% of submitted ideas fall in one domain. If so, that domain is pre-highlighted in Q1 as a suggested default. Rationale: a user consistently evaluating procurement ideas is likely working in that space, and reducing clicks improves UX.

**Similar-idea notice:** Phase ≥ 1 users see a notice on Q1 when they've previously submitted an idea in the same domain. This prevents duplicate evaluation effort and surfaces historical context.

**Onboarding fields collected:**

| Field | Purpose |
|-------|---------|
| Name | Personalization display only |
| Role | Calibrates stakeholder framing in research plans |
| Org type | Calibrates domain relevance (e.g., 3PL vs. OEM) |
| Org size | Calibrates scale assumptions in research plans |
| Region | Drives compliance-related framing (EMEA vs. APAC trade rules differ) |
| Primary domains | Pre-populates Q1 suggestion and ordering |
| Data systems | Injects specific ERP/system names into research plan data pull section |
| Preferred research methods | Orders the Methods tab by preference |

**Why collect this upfront:** The onboarding data directly improves research plan specificity. Without knowing the user's data systems, the research plan can only say "check your ERP." With it, it says "pull from SAP S/4HANA transaction ME2N" — a meaningfully more actionable instruction.

---

## 9. Domain Coverage

### Live Domains

| Domain | Q2 Options | Q3 Primary Stakeholder | Research Template |
|--------|-----------|----------------------|------------------|
| Planning & Forecasting | 6 | SC Planners | Forecast accuracy, inventory, S&OP |
| Procurement & Sourcing | 6 | Procurement Mgrs | Invoice matching, supplier risk, spend |
| Repair & MRO | 7 | Operations | MTTR, parts availability, warranty |

### Pending Domains (WIP)

| Domain | Status | Blocker |
|--------|--------|---------|
| Trade & Compliance | Hidden (`hidden: true`) | Q2 branching options + research templates needed |
| Fraud & Risk | Hidden (`hidden: true`) | Q2 branching options + research templates needed |

**To re-enable a WIP domain:** In `config/questions.yaml`, find the Q1 option for the domain and change `hidden: false` and `wip: false`. The scoring engine, Q2 options, Q3 ordering, and research plan templates are already scaffolded — they will activate automatically.

---

## 10. Config File Map

| File | Purpose | Key Sections |
|------|---------|-------------|
| `config/questions.yaml` | All questions, options, scores, adaptive branching | `pre_question`, `questions[q1-q5]`, `domain_options` |
| `config/scoring.yaml` | Dimension weights, verdict bands, confidence flag rules | `dimensions`, `verdict_bands`, `confidence_flags` |
| `config/user_context.yaml` | User profile, phase, custom extensions, scoring overrides | `profile`, `phase`, `custom_extensions`, `scoring_customization` |
| `config/llm_config.yaml` | LLM provider selection, model, timeout, token limits | `provider`, `model`, `max_tokens` |
| `data/ideas.json` | Persistent idea history (appended on each submission) | Array of idea objects with domain, score, date, answers |
| `.streamlit/config.toml` | Streamlit theme (light mode, brand colors) | `[theme]` section |
| `.env` | Environment variables (API keys) — **never commit this** | `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` |

---

## 11. Key Architectural Decisions

### Why Streamlit?

Streamlit allows rapid prototyping of data-driven UIs in pure Python — no frontend skills required. The entire UI state machine is driven by `st.session_state`. The tradeoff is that complex multi-page flows require careful state management (all answers are stored in `st.session_state.engine.answers`).

**Session state architecture:** Each screen is a function (`screen_q1()`, `screen_verdict()`, etc.). Navigation is driven by `st.session_state.screen`. The `QuestionEngine` instance is cached with `@st.cache_resource` to persist across reruns.

### Why YAML for config, not a database?

For a single-user tool, YAML provides the best balance of human readability (easy to edit by hand), version control friendliness (diffs are meaningful), and zero infrastructure overhead. A database would add deployment complexity without benefit at this scale.

### The `safe_radio()` Pattern

A critical Streamlit behavior: `st.radio(index=None)` returns `None` before the user interacts. If code downstream calls `labels.index(current_value)`, it raises `ValueError: None is not in list`. The `safe_radio()` wrapper in `app.py` enforces `index=0` as the minimum, preventing this on all question screens. Any new question screens added in the future must use `safe_radio()` rather than `st.radio()` directly.

### Why Not Store Ideas in a Database?

`data/ideas.json` is an append-only JSON array. It's intentionally simple: no schema migrations, no query language needed, and the data volume (hundreds of ideas at most) doesn't warrant a database. The `UserContextManager` loads the full array into memory on startup. If idea volume grows to thousands, migrate to SQLite — the interface (`get_ideas_history()`, `record_idea_submitted()`) is already abstracted.

### LLM Provider Abstraction

`llm/base.py` defines `BaseLLMProvider`. `llm/factory.py` reads `config/llm_config.yaml` to instantiate either `ClaudeProvider` or `OpenAIProvider`. Adding a new LLM requires only:
1. Creating `llm/new_provider.py` implementing `BaseLLMProvider`
2. Adding a case to `LLMFactory`
3. Updating `config/llm_config.yaml`

No changes to `app.py` or `research_planner.py` are needed.

---

## 12. Known Limitations & Planned Improvements

### Current Limitations

**Single-user only:** `user_context.yaml` and `data/ideas.json` are local files. There is no multi-user support or authentication. For team deployment, these would need to be replaced with a shared store (SQLite, Postgres, or a cloud key-value store).

**No outcome tracking yet:** Phase 3 promises outcome tracking (did the idea get built? did it succeed?), but the data model and UI are not yet implemented. The `ideas.json` schema has a placeholder `outcome` field.

**Trade & Fraud domains incomplete:** These two domains are hidden pending fuller Q2 branching options and domain-specific research templates (Task 8).

**Research plan is one-shot:** The plan is generated once at verdict time and not regeneratable from the same idea without re-evaluating. A "Regenerate plan" button with optional additional context would improve this.

**No export to project management tools:** Idea cards and research plans are viewable in-app but not exportable to Jira, Linear, Notion, or Asana. This is a high-value future integration.

### Planned Improvements (Task 8 and beyond)

- **Task 8:** Domain research for Trade & Compliance and Fraud & Risk — Q2 adaptive options, Q3 ordering, and research plan templates
- **Outcome feedback loop:** Let users mark whether the idea was built and whether it succeeded; use this to recalibrate scores over time
- **Team mode:** Shared idea backlog with role-based views (PM, engineering, leadership)
- **Idea comparison:** Side-by-side scoring of two ideas to help triage competing priorities
- **Webhook / integration layer:** Push verdict + research plan to Notion page, Jira ticket, or Slack channel on submission
- **CSV export:** Batch export of all evaluated ideas with scores and dimensions for portfolio-level analysis

---

*Last updated: May 2026*
*Primary author: Product Skout design sessions, Avinash Talluri*
