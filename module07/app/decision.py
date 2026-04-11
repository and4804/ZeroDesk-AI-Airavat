"""
M07 Decision Logic — aggregate rule results into PASS / REFER / REJECT.

Priority: REJECT > HALT > REFER > PASS

HALT (R08 — no consent) is mapped to REFER in the final decision because
the bureau_responses.eligibility_decision column only supports
PASS | REFER | REJECT.
"""

from __future__ import annotations

from app.models import RuleEvaluation


def derive_decision(rules_results: list[RuleEvaluation]) -> str:
    """
    Scan all rule evaluations and return the final eligibility decision.

    Returns
    -------
    str
        ``"PASS"`` if all rules passed,
        ``"REJECT"`` if any rule with REJECT action failed,
        ``"REFER"`` if any rule with REFER or HALT action failed
        (but no REJECT failures).
    """
    has_reject = False
    has_refer = False

    for rule in rules_results:
        if rule.passed:
            continue

        action = rule.action_on_fail.upper()
        if action == "REJECT":
            has_reject = True
        elif action in ("REFER", "HALT"):
            has_refer = True

    if has_reject:
        return "REJECT"
    if has_refer:
        return "REFER"
    return "PASS"
