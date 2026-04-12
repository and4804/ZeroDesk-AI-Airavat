"""
M07 Rules Engine — evaluates eligibility gates R01–R08.

Every rule runs regardless of prior failures (no short-circuit) so the
complete audit trail is always available.

Cross-module signals (fraud_score, liveness_avg, consent_detected) are
accepted as parameters with assumed defaults from config.
"""

from __future__ import annotations

from typing import Any

from app.config import CURRENT_YEAR, load_rules_config
from app.models import DpdEntry, RuleEvaluation


def _has_dpd_last_12m(dpd_history: list[DpdEntry]) -> bool:
    """Return True if there are any DPD events in the current year (last ~12 months)."""
    return any(entry.year >= CURRENT_YEAR for entry in dpd_history)


def _evaluate_operator(actual: Any, operator: str, threshold: Any) -> bool:
    """
    Evaluate ``actual <operator> threshold`` and return True if the
    condition is **satisfied** (i.e. the rule passes).
    """
    if operator == ">=":
        return actual >= threshold
    if operator == "<=":
        return actual <= threshold
    if operator == "==":
        # Special: threshold=null means "must be empty / None / false-ish"
        if threshold is None:
            return not actual  # passes when the value is falsy (empty list, 0, etc.)
        return actual == threshold
    if operator == ">":
        return actual > threshold
    if operator == "<":
        return actual < threshold
    if operator == "!=":
        return actual != threshold
    raise ValueError(f"Unsupported operator: {operator}")


def evaluate_rules(
    *,
    credit_score: int,
    written_off_accounts: int,
    foir: float,
    dpd_history: list[DpdEntry],
    active_loan_count: int,
    fraud_score: int,
    liveness_avg: float,
    consent_detected: bool,
) -> list[RuleEvaluation]:
    """
    Run all R01–R08 eligibility gates and return per-rule results.

    Parameters come from the bureau response fields and cross-module
    signals (with assumed defaults when running standalone).
    """
    rules = load_rules_config()
    results: list[RuleEvaluation] = []

    # Build a lookup of actual values keyed by the ``field`` name used
    # in rules_config.json.
    field_values: dict[str, Any] = {
        "credit_score": credit_score,
        "written_off_accounts": written_off_accounts,
        "foir": foir,
        "dpd_last_12m": _has_dpd_last_12m(dpd_history),  # bool
        "active_loan_count": active_loan_count,
        "fraud_score": fraud_score,
        "liveness_avg": liveness_avg,
        "consent_detected": consent_detected,
    }

    for rule in rules:
        rule_id: str = rule["rule_id"]
        field: str = rule["field"]
        operator: str = rule["operator"]
        threshold: Any = rule["threshold"]
        action_on_fail: str = rule["action_on_fail"]
        rule_name: str = rule.get("rule_name", rule_id)

        actual_value = field_values.get(field)

        passed = _evaluate_operator(actual_value, operator, threshold)

        results.append(RuleEvaluation(
            rule_id=rule_id,
            rule_name=rule_name,
            passed=passed,
            value=actual_value,
            threshold=threshold,
            action_on_fail=action_on_fail,
        ))

    return results
