---
name: Skout project state
description: Current state of the Skout PM ideation tool codebase
type: project
---

Skout v0.5 -- Supply Chain Edition. All tasks through the role-based sidebar sprint are complete as of 2026-05-03.

**What shipped:**
- core/constants.py -- single source of truth for all label dicts (Q2-Q6, DOMAIN_LABELS)
- data/research_content.json -- all static lookup tables extracted from research_planner.py (82KB JSON)
- core/research_planner.py -- refactored from ~1390 to ~489 lines (64% reduction)
- core/team_manager.py -- TeamManager class with detect_adjacencies(), get_director_stats(), flag_for_collaboration()
- core/integrations.py -- share_to_team() now stores problem_id, stakeholder_id, collaboration flag fields
- core/user_context_manager.py -- get_role_type(), get_team_id() methods; apply_onboarding() accepts role_type + team_id
- config/user_context.yaml -- profile now has role_type: pm, team_id: default
- app.py -- three sidebar helper functions (_sidebar_pm_panel, _sidebar_teamlead_panel, _sidebar_director_panel); onboarding form has role_type selectbox + team_id input; TeamManager imported

**Architecture notes:**
- Three roles: pm | team_lead | director (stored in UCM profile)
- PM sidebar: personal history + adjacency alerts (strong=same problem, moderate=same stakeholder)
- Team Lead sidebar: team pool list + flag-for-collaboration expander + flagged pairs summary
- Director sidebar: read-only portfolio (domain counts, score bands, top 5, cross-domain signals)
- team_id scopes the shared idea pool; default is "default"

**Why:** Token cost reduction (23% codebase shrink) + team collaboration layer for multi-PM supply chain teams.
