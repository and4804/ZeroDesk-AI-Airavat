"""
Tests for Rules Engine (app/rules_engine.py) and Decision Logic (app/decision.py).
"""

import pytest

from app.decision import derive_decision
from app.models import DpdEntry
from app.rules_engine import evaluate_rules


def _default_kwargs(**overrides):
    """Return a baseline set of kwargs that passes all rules, with overrides."""
    base = {
        "credit_score": 750,
        "written_off_accounts": 0,
        "foir": 0.30,
        "dpd_history": [],
        "active_loan_count": 1,
        "fraud_score": 20,
        "liveness_avg": 0.90,
        "consent_detected": True,
    }
    base.update(overrides)
    return base


class TestRulesEngine:
    """Test individual rules R01–R08."""

    def test_all_pass(self):
        results = evaluate_rules(**_default_kwargs())
        assert all(r.passed for r in results)
        assert derive_decision(results) == "PASS"

    # ── R01: credit_score >= 650 → REJECT ────────────────────────────
    def test_r01_reject_low_score(self):
        results = evaluate_rules(**_default_kwargs(credit_score=600))
        r01 = next(r for r in results if r.rule_id == "R01")
        assert not r01.passed
        assert r01.action_on_fail == "REJECT"
        assert derive_decision(results) == "REJECT"

    def test_r01_pass_boundary(self):
        results = evaluate_rules(**_default_kwargs(credit_score=650))
        r01 = next(r for r in results if r.rule_id == "R01")
        assert r01.passed

    # ── R02: written_off_accounts == 0 → REJECT ─────────────────────
    def test_r02_reject_writeoff(self):
        results = evaluate_rules(**_default_kwargs(written_off_accounts=1))
        r02 = next(r for r in results if r.rule_id == "R02")
        assert not r02.passed
        assert derive_decision(results) == "REJECT"

    # ── R03: foir <= 0.50 → REJECT ───────────────────────────────────
    def test_r03_reject_high_foir(self):
        results = evaluate_rules(**_default_kwargs(foir=0.65))
        r03 = next(r for r in results if r.rule_id == "R03")
        assert not r03.passed
        assert derive_decision(results) == "REJECT"

    def test_r03_pass_boundary(self):
        results = evaluate_rules(**_default_kwargs(foir=0.50))
        r03 = next(r for r in results if r.rule_id == "R03")
        assert r03.passed

    # ── R04: dpd_last_12m == None (empty) → REFER ────────────────────
    def test_r04_refer_recent_dpd(self):
        dpd = [DpdEntry(days=30, count=1, year=2026)]
        results = evaluate_rules(**_default_kwargs(dpd_history=dpd))
        r04 = next(r for r in results if r.rule_id == "R04")
        assert not r04.passed
        assert r04.action_on_fail == "REFER"
        assert derive_decision(results) == "REFER"

    def test_r04_pass_old_dpd(self):
        dpd = [DpdEntry(days=30, count=1, year=2024)]  # old, not last 12m
        results = evaluate_rules(**_default_kwargs(dpd_history=dpd))
        r04 = next(r for r in results if r.rule_id == "R04")
        assert r04.passed

    # ── R05: active_loan_count <= 4 → REFER ──────────────────────────
    def test_r05_refer_too_many_loans(self):
        results = evaluate_rules(**_default_kwargs(active_loan_count=6))
        r05 = next(r for r in results if r.rule_id == "R05")
        assert not r05.passed
        assert derive_decision(results) == "REFER"

    # ── R06: fraud_score <= 60 → REJECT ──────────────────────────────
    def test_r06_reject_high_fraud(self):
        results = evaluate_rules(**_default_kwargs(fraud_score=82))
        r06 = next(r for r in results if r.rule_id == "R06")
        assert not r06.passed
        assert derive_decision(results) == "REJECT"

    # ── R07: liveness_avg >= 0.6 → REJECT ────────────────────────────
    def test_r07_reject_low_liveness(self):
        results = evaluate_rules(**_default_kwargs(liveness_avg=0.45))
        r07 = next(r for r in results if r.rule_id == "R07")
        assert not r07.passed
        assert derive_decision(results) == "REJECT"

    # ── R08: consent_detected == true → HALT ─────────────────────────
    def test_r08_halt_no_consent(self):
        results = evaluate_rules(**_default_kwargs(consent_detected=False))
        r08 = next(r for r in results if r.rule_id == "R08")
        assert not r08.passed
        assert r08.action_on_fail == "HALT"
        # HALT maps to REFER in final decision
        assert derive_decision(results) == "REFER"


class TestDecisionPriority:
    """Test that REJECT takes priority over REFER/HALT."""

    def test_reject_wins_over_refer(self):
        results = evaluate_rules(**_default_kwargs(
            credit_score=600,       # R01 → REJECT
            active_loan_count=6,    # R05 → REFER
        ))
        assert derive_decision(results) == "REJECT"

    def test_reject_wins_over_halt(self):
        results = evaluate_rules(**_default_kwargs(
            fraud_score=82,          # R06 → REJECT
            consent_detected=False,  # R08 → HALT
        ))
        assert derive_decision(results) == "REJECT"

    def test_multiple_refers(self):
        dpd = [DpdEntry(days=30, count=1, year=2026)]
        results = evaluate_rules(**_default_kwargs(
            dpd_history=dpd,         # R04 → REFER
            active_loan_count=5,     # R05 → REFER
        ))
        assert derive_decision(results) == "REFER"
