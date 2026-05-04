# Git Upload Instructions — Skout

## First-time setup (do this once)

### 1. Install Git
Download from https://git-scm.com/download/win and install with defaults.

### 2. Create a GitHub account (if you don't have one)
Go to https://github.com and sign up.

### 3. Create a new repository on GitHub
- Click **"New"** (green button, top-left)
- Name it: `skout` (or `supply-chain-evaluator`)
- Set it to **Private** (recommended — your domain knowledge is valuable IP)
- Do NOT check "Add README" or "Add .gitignore" — we already have these
- Click **"Create repository"**
- Copy the repository URL shown (looks like `https://github.com/YOUR_USERNAME/skout.git`)

---

## Upload your code

Open a terminal in the `skout/` folder (right-click the folder → "Open in Terminal" on Windows).

```bash
# Step 1: Initialise git in the project folder
git init

# Step 2: Set your identity (one-time)
git config --global user.name "Avinash"
git config --global user.email "tavinash87@gmail.com"

# Step 3: Stage everything (the .gitignore already excludes .env and secrets)
git add .

# Step 4: Verify what's being committed (optional but recommended)
git status

# Step 5: First commit
git commit -m "Initial commit: Skout with 7 domain knowledge patterns"

# Step 6: Connect to GitHub (paste YOUR repository URL from Step 3 above)
git remote add origin https://github.com/atallam/PMSkout.git

# Step 7: Push to GitHub
git branch -M main
git push -u origin main
```

That's it — your code is on GitHub.

---

## Every time you make changes (ongoing workflow)

```bash
# See what changed
git status

# Stage all changes
git add .

# Commit with a meaningful message
git commit -m "Add KPI benchmarks for pharma industry"

# Push to GitHub
git push
```

---

## What IS committed (safe)

```
skout/
├── app.py                          ✅ Main Streamlit app
├── core/
│   ├── challenger_agent.py         ✅ Pattern #2
│   ├── kpi_validator.py            ✅ Pattern #3
│   ├── rag_store.py                ✅ Pattern #4
│   ├── domain_scorer.py            ✅ Pattern #6
│   ├── context_checker.py          ✅ Pattern #7
│   ├── domain_knowledge_engine.py  ✅ Master orchestrator
│   ├── scoring_engine.py           ✅ Existing
│   └── ...
├── domain_knowledge/
│   ├── kpi_benchmarks.json         ✅ KPI data
│   ├── failure_patterns.json       ✅ Failure patterns
│   └── scor_framework.md           ✅ SCOR knowledge
├── tests/adversarial_cases/        ✅ Test suite
├── config/                         ✅ YAML configs
├── .gitignore                      ✅ Excludes secrets
└── requirements.txt                ✅ Dependencies
```

## What is NOT committed (.gitignore protects these)

```
.env                    ❌ Your API keys — NEVER commit this
__pycache__/            ❌ Python cache
venv/                   ❌ Virtual environment
data/ideas.json         ❌ Your local idea data
```

---

## Quick reference — common Git commands

| Command | What it does |
|---|---|
| `git status` | See what files changed |
| `git add .` | Stage all changes |
| `git commit -m "message"` | Save a snapshot |
| `git push` | Upload to GitHub |
| `git pull` | Download latest from GitHub |
| `git log --oneline` | See commit history |
| `git diff` | See exact line changes |

---

## Deploying to Streamlit Cloud (hosting)

Once your code is on GitHub:

1. Go to https://share.streamlit.io
2. Sign in with your GitHub account
3. Click **"New app"**
4. Select your `skout` repository
5. Set **Main file path**: `app.py`
6. Click **"Advanced settings"** → add your secrets:
   ```
   ANTHROPIC_API_KEY = "sk-ant-..."
   OPENAI_API_KEY = "sk-..."
   ```
7. Click **"Deploy"** — your app will be live at `https://YOUR_APP.streamlit.app`

The `.streamlit/config.toml` file you already have will be picked up automatically.
