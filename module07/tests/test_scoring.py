"""
Tests for CIBIL score calculator (app/scoring.py).
"""

import pytest

from app.models import CreditMixAge, CreditUtilization, NewCredit, PaymentHistory
from app.scoring import (
    calculate_credit_score,
    score_mix_age,
    score_new_credit,
    score_payment_history,
    score_utilization,
)


# ---------------------------------------------------------------------------
# Sub-score tests
# ---------------------------------------------------------------------------

class TestPaymentHistoryScore:
    def test_perfect_history(self):
        ph = PaymentHistory(on_time_pct=100, dpd_30_count=0, dpd_60_count=0, dpd_90_count=0)
        assert score_payment_history(ph) == 100.0

    def test_some_dpd_30(self):
        ph = PaymentHistory(on_time_pct=95, dpd_30_count=2, dpd_60_count=0, dpd_90_count=0)
        assert score_payment_history(ph) == 85.0  # 95 - 10

    def test_severe_dpd_90(self):
        ph = PaymentHistory(on_time_pct=70, dpd_30_count=0, dpd_60_count=0, dpd_90_count=3)
        assert score_payment_history(ph) == 0.0  # 70 - 90 → clamped to 0

    def test_mixed_dpd(self):
        ph = PaymentHistory(on_time_pct=90, dpd_30_count=1, dpd_60_count=1, dpd_90_count=0)
        assert score_payment_history(ph) == 70.0  # 90 - 5 - 15


class TestUtilizationScore:
    def test_zero_utilization(self):
        cu = CreditUtilization(total_limit=500000, current_balance=0)
        assert score_utilization(cu) == 100.0

    def test_full_utilization(self):
        cu = CreditUtilization(total_limit=100000, current_balance=100000)
        assert score_utilization(cu) == 0.0

    def test_thirty_percent(self):
        cu = CreditUtilization(total_limit=100000, current_balance=30000)
        assert score_utilization(cu) == 70.0

    def test_no_credit_limit(self):
        cu = CreditUtilization(total_limit=0, current_balance=0)
        assert score_utilization(cu) == 50.0  # neutral


class TestMixAgeScore:
    def test_no_history(self):
        cma = CreditMixAge(secured_count=0, unsecured_count=0, oldest_account_months=0)
        assert score_mix_age(cma) == 0.0

    def test_diverse_mix_long_history(self):
        cma = CreditMixAge(secured_count=2, unsecured_count=1, oldest_account_months=120)
        score = score_mix_age(cma)
        assert score > 90.0  # 40 mix + ~60 age

    def test_only_unsecured(self):
        cma = CreditMixAge(secured_count=0, unsecured_count=3, oldest_account_months=36)
        score = score_mix_age(cma)
        assert 0 < score < 50  # no mix bonus, some age bonus


class TestNewCreditScore:
    def test_no_enquiries(self):
        nc = NewCredit(enquiries_last_6m=0, new_accounts_last_6m=0)
        assert score_new_credit(nc) == 100.0

    def test_many_enquiries(self):
        nc = NewCredit(enquiries_last_6m=7, new_accounts_last_6m=0)
        assert score_new_credit(nc) == 0.0  # 100 - 105 → clamped to 0

    def test_moderate_activity(self):
        nc = NewCredit(enquiries_last_6m=2, new_accounts_last_6m=1)
        assert score_new_credit(nc) == 50.0  # 100 - 30 - 20


# ---------------------------------------------------------------------------
# Full score calculation
# ---------------------------------------------------------------------------

class TestCalculateCreditScore:
    def test_perfect_profile_near_900(self):
        score = calculate_credit_score(
            PaymentHistory(on_time_pct=100),
            CreditUtilization(total_limit=1000000, current_balance=50000),
            CreditMixAge(secured_count=2, unsecured_count=1, oldest_account_months=144),
            NewCredit(enquiries_last_6m=0, new_accounts_last_6m=0),
        )
        assert 850 <= score <= 900

    def test_worst_profile_near_300(self):
        score = calculate_credit_score(
            PaymentHistory(on_time_pct=30, dpd_30_count=5, dpd_60_count=3, dpd_90_count=2),
            CreditUtilization(total_limit=100000, current_balance=100000),
            CreditMixAge(secured_count=0, unsecured_count=0, oldest_account_months=0),
            NewCredit(enquiries_last_6m=10, new_accounts_last_6m=5),
        )
        assert score == 300

    def test_score_in_valid_range(self):
        score = calculate_credit_score(
            PaymentHistory(on_time_pct=80, dpd_30_count=1),
            CreditUtilization(total_limit=200000, current_balance=80000),
            CreditMixAge(secured_count=1, unsecured_count=1, oldest_account_months=36),
            NewCredit(enquiries_last_6m=2, new_accounts_last_6m=0),
        )
        assert 300 <= score <= 900
