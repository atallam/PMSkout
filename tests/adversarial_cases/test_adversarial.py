"""
Skout — Pattern #5: Adversarial Test Suite
============================================
Tests the domain knowledge engine against cases that MUST be blocked.
Any must_fail case that passes is a domain knowledge regression.

Run:
    cd skout
    pytest tests/adversarial_cases/test_adversarial.py -v
    pytest tests/adversarial_cases/test_adversarial.py -v --tb=short   # compact output
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

# Ensure the skout root is on the path
SKOUT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(SKOUT_ROOT))
os.chdir(SKOUT_ROOT)

from core.domain_knowledge_engine import DomainKnowledgeEngine


# ------------------------------------------------------------------ #
# Load test cases
# ------------------------------------------------------------------ #

CASES_FILE = Path(__file__).parent / "cases.json"

with open(CASES_FILE, encoding="utf-8") as f:
    _CASES = json.load(f)

MUST_FAIL_CASES = _CASES["must_fail"]
SHOULD_PASS_CASES = _CASES["should_pass"]


# ------------------------------------------------------------------ #
# Engine fixture (rule-based only for CI — no API key needed)
# ------------------------------------------------------------------ #

@pytest.fixture(scope="module")
def engine():
    """Rule-based engine — safe for CI without API keys."""
    return DomainKnowledgeEngine(llm_provider=None, use_llm=False)


# ------------------------------------------------------------------ #
# Must-Fail Tests: these MUST be blocked or conditional
# A PASS on a must-fail case is a domain knowledge regression
# ------------------------------------------------------------------ #

@pytest.mark.parametrize("case", MUST_FAIL_CASES, ids=[c["id"] for c in MUST_FAIL_CASES])
def test_must_fail_cases(engine, case):
    """
    Each must-fail case must NOT receive a clean PASS verdict.
    Acceptable outcomes: BLOCK, CONDITIONAL, INSUFFICIENT_CONTEXT.
    """
    result = engine.evaluate(
        recommendation=case["recommendation"],
        context=case["context"],
    )

    # A must-fail case should NEVER receive a clean PASS
    assert result.overall_verdict != "PASS", (
        f"\n{'='*60}\n"
        f"REGRESSION: Case {case['id']} — {case['name']}\n"
        f"Expected: BLOCK or CONDITIONAL\n"
        f"Got: {result.overall_verdict}\n"
        f"Reason: {case['reason']}\n"
        f"Challenger findings: {len(result.challenger_summary.get('total', 0))} challenges\n"
        f"Domain score: {result.domain_score.score_pct}%\n"
        f"{'='*60}"
    )

    print(f"\n✅ {case['id']} correctly blocked/flagged as {result.overall_verdict}")
    print(f"   Risk level: {result.risk_level}")
    print(f"   Challenges found: {result.challenger_summary.get('total', 0)}")


@pytest.mark.parametrize("case", MUST_FAIL_CASES, ids=[c["id"] for c in MUST_FAIL_CASES])
def test_must_fail_has_challenges(engine, case):
    """Must-fail cases must generate at least one challenge."""
    result = engine.evaluate(
        recommendation=case["recommendation"],
        context=case["context"],
    )
    challenge_count = result.challenger_summary.get("total", 0)
    assert challenge_count > 0, (
        f"Case {case['id']}: Expected challenges but found none. "
        f"Recommendation: {case['recommendation'][:100]}..."
    )


@pytest.mark.parametrize("case", MUST_FAIL_CASES, ids=[c["id"] for c in MUST_FAIL_CASES])
def test_must_fail_risk_level(engine, case):
    """Must-fail cases must be rated MEDIUM risk or higher."""
    result = engine.evaluate(
        recommendation=case["recommendation"],
        context=case["context"],
    )
    assert result.risk_level in ("MEDIUM", "HIGH", "CRITICAL"), (
        f"Case {case['id']}: Risk level should be at least MEDIUM, got {result.risk_level}"
    )


# ------------------------------------------------------------------ #
# Should-Pass Tests: well-scoped recommendations should pass
# ------------------------------------------------------------------ #

@pytest.mark.parametrize("case", SHOULD_PASS_CASES, ids=[c["id"] for c in SHOULD_PASS_CASES])
def test_should_pass_cases(engine, case):
    """
    Each should-pass case should receive PASS or CONDITIONAL.
    BLOCK on a well-designed recommendation is a false positive.
    """
    result = engine.evaluate(
        recommendation=case["recommendation"],
        context=case["context"],
    )

    assert result.overall_verdict in ("PASS", "CONDITIONAL"), (
        f"\n{'='*60}\n"
        f"FALSE POSITIVE: Case {case['id']} — {case['name']}\n"
        f"Expected: PASS or CONDITIONAL\n"
        f"Got: {result.overall_verdict} — {result.reasoning[:200]}\n"
        f"Reason: {case['reason']}\n"
        f"{'='*60}"
    )

    print(f"\n✅ {case['id']} correctly approved as {result.overall_verdict}")


# ------------------------------------------------------------------ #
# Regression summary
# ------------------------------------------------------------------ #

def test_engine_loads_knowledge_base(engine):
    """RAG store should load without errors and have content."""
    stats = engine.rag_store.stats()
    assert stats["total_chunks"] > 0, "RAG store loaded no knowledge chunks — check domain_knowledge/ files."
    print(f"\n📚 RAG store loaded {stats['total_chunks']} chunks: {stats['by_category']}")


def test_engine_responds_to_empty_input(engine):
    """Engine should handle empty input gracefully."""
    result = engine.evaluate(recommendation="", context={})
    assert result is not None
    assert result.overall_verdict in ("PASS", "CONDITIONAL", "BLOCK", "INSUFFICIENT_CONTEXT")


if __name__ == "__main__":
    # Can also run directly: python test_adversarial.py
    import subprocess
    subprocess.run(
        ["pytest", __file__, "-v", "--tb=short"],
        cwd=str(SKOUT_ROOT),
    )
