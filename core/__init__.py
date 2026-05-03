"""
Skout — Core Engine Package
============================
All domain logic for Product Skout lives here. These modules are LLM-agnostic
and depend only on config files under config/.

Modules:
  question_engine       — Adaptive 5-question flow (branching on Q1 domain).
  scoring_engine        — Rule-based verdict scoring with SCOR / WSJF / ODI metrics.
  research_planner      — Domain-aware research plan generator (rule-based + LLM).
  idea_card             — Structured idea card generator with research gate check.
  user_context_manager  — Personalisation, phase tracking, and context injection.
  domain_knowledge_engine — Master orchestrator for the 7 domain audit patterns.
  challenger_agent      — Pattern #2: Devil's advocate failure mode surfacing.
  kpi_validator         — Pattern #3: Benchmark-anchored KPI warning system.
  rag_store             — Pattern #4: Keyword-based domain knowledge retrieval.
  domain_scorer         — Pattern #6: Multi-dimensional supply chain scorecard.
  context_checker       — Pattern #7: Context completeness validator.

Standard import pattern:
    from core.question_engine import QuestionEngine
    from core.scoring_engine  import ScoringEngine, VerdictResult
"""
