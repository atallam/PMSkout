# Skout v0.1 — Quick Start

## Install dependencies
```bash
cd skout
pip install -r requirements.txt
```

## Set your API key (optional — works without one in rule-based mode)
```bash
# Windows
set ANTHROPIC_API_KEY=sk-ant-...

# Mac/Linux
export ANTHROPIC_API_KEY=sk-ant-...
```

## Run Skout
```bash
streamlit run app.py
```
Then open http://localhost:8501 in your browser.

---

## Modes

| Mode | LLM needed | What it does |
|------|-----------|--------------|
| Quick Scan | No | Rule-based scoring only, <3 sec |
| Standard | Yes (Haiku) | Adaptive research plan + hypothesis, ~15 sec |
| Deep Research | Yes (Sonnet) | Ultrathink — 3 competing hypotheses, counter-arguments, ~60 sec |

Deep Research activates automatically when verdict score ≥ 80.

---

## Personalise Skout for your context
Edit `config/user_context.yaml` to set:
- Your role, organisation type, and primary domains
- Custom data sources (SAP, ServiceNow, etc.)
- Preferred interview count and research methods
- Custom scoring weights (unlocks after 5 ideas)
- Custom domain extensions (e.g. "Network Spare Parts" under Repair)

---

## File structure
```
skout/
├── config/
│   ├── questions.yaml      ← All question content, options, branching
│   ├── scoring.yaml        ← Verdict bands, dimension weights, flags
│   ├── llm_config.yaml     ← LLM provider and mode config
│   └── user_context.yaml   ← Your personal context (edit this)
├── core/
│   ├── question_engine.py  ← Adaptive question flow
│   ├── scoring_engine.py   ← Verdict score calculator
│   ├── research_planner.py ← Research plan generator
│   └── idea_card.py        ← Idea card builder
├── llm/
│   ├── claude_provider.py  ← Anthropic Claude (standard + deep think)
│   ├── openai_provider.py  ← OpenAI GPT fallback
│   └── factory.py          ← Auto-selects best available provider
├── app.py                  ← Streamlit UI (run this)
└── requirements.txt
```

## What's next (v0.2+)
- Fraud & Trade Compliance deep branching (domain research in progress)
- User context personalisation layer (auto-learns from usage)
- PDF export for Idea Card
- Spec/PRD template launcher
