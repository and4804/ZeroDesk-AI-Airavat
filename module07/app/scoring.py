"""
M07 CIBIL Score Calculator — weighted sub-score approach.

Weights (user-specified):
    Payment History   35%
    Utilization       25%
    Credit Mix & Age  20%
    New Credit        20%

Each factor produces a sub-score on a 0–100 scale.  The weighted average
is then mapped onto the 300–900 CIBIL range.
"""

from __future__ import annotations

import math

from app.config import SCORE_WEIGHTS
from app.models import (
    CreditMixAge,
    CreditUtilization,
    NewCredit,
    PaymentHistory,
)


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


# ---------------------------------------------------------------------------
# Sub-score calculators  (each returns 0–100)
# ---------------------------------------------------------------------------

def score_payment_history(ph: PaymentHistory) -> float:
    """
    Start from on_time_pct, penalise by DPD severity:
      -5  per DPD-30 event
      -15 per DPD-60 event
      -30 per DPD-90 event
    """
    raw = ph.on_time_pct
    raw -= ph.dpd_30_count * 5
    raw -= ph.dpd_60_count * 15
    raw -= ph.dpd_90_count * 30
    return _clamp(raw)


def score_utilization(cu: CreditUtilization) -> float:
    """
    Utilisation ratio = current_balance / total_limit.
    Lower is better → sub-score = 100 - (ratio × 100).
    """
    if cu.total_limit <= 0:
        return 50.0  # no credit history — neutral
    ratio = cu.current_balance / cu.total_limit
    return _clamp(100.0 - ratio * 100.0)


def score_mix_age(cma: CreditMixAge) -> float:
    """
    Mix diversity bonus (0–40 pts):
        +20 if has ≥1 secured account
        +20 if has healthy mix (both secured & unsecured)
    Age curve (0–60 pts):
        Logarithmic: 60 × log2(1 + months) / log2(1 + 120), capped at 120.
    """
    mix_pts = 0.0
    if cma.secured_count >= 1:
        mix_pts += 20.0
    if cma.secured_count >= 1 and cma.unsecured_count >= 1:
        mix_pts += 20.0

    capped_months = min(cma.oldest_account_months, 120)
    if capped_months > 0:
        age_pts = 60.0 * math.log2(1 + capped_months) / math.log2(1 + 120)
    else:
        age_pts = 0.0

    return _clamp(mix_pts + age_pts)


def score_new_credit(nc: NewCredit) -> float:
    """
    Start at 100.
      -15 per enquiry in last 6 months
      -20 per new account in last 6 months
    """
    raw = 100.0
    raw -= nc.enquiries_last_6m * 15
    raw -= nc.new_accounts_last_6m * 20
    return _clamp(raw)


# ---------------------------------------------------------------------------
# Main calculator
# ---------------------------------------------------------------------------

def calculate_credit_score(
    payment_history: PaymentHistory,
    credit_utilization: CreditUtilization,
    credit_mix_age: CreditMixAge,
    new_credit: NewCredit,
) -> int:
    """
    Compute a CIBIL-style credit score in the 300–900 range.

    If a seed profile already carries a preset ``credit_score``, that value
    should be used directly; this function is for dynamic calculation.
    """
    sub_scores = {
        "payment_history": score_payment_history(payment_history),
        "utilization": score_utilization(credit_utilization),
        "mix_age": score_mix_age(credit_mix_age),
        "new_credit": score_new_credit(new_credit),
    }

    weighted_avg = sum(
        sub_scores[key] * SCORE_WEIGHTS[key] for key in SCORE_WEIGHTS
    )

    # Map 0–100 → 300–900
    raw_score = 300 + (weighted_avg / 100.0) * 600
    return int(_clamp(raw_score, 300, 900))
