"""
M07 — Mock Bureau Integration & Policy-Based Eligibility Engine
Calls the bureau-mock microservice and applies configurable policy rules.
"""

import json
from datetime import datetime
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import httpx

from config import settings
from database import get_db
from session_store import store
from events import audit

router = APIRouter(prefix="/api/bureau", tags=["M07 - Bureau"])


# ──────────────────────────────────────────────────────────────────
# Policy Rules (Configurable)
# ──────────────────────────────────────────────────────────────────

POLICY_RULES = {
    "min_credit_score": {
        "threshold": 600,
        "description": "Minimum credit score required for approval",
    },
    "max_emi_to_income_ratio": {
        "threshold": 0.50,
        "description": "EMI should not exceed 50% of monthly income",
    },
    "max_active_loans": {
        "threshold": 5,
        "description": "Maximum number of active loans allowed",
    },
    "max_dpd_days": {
        "threshold": 90,
        "description": "Maximum days past due in recent history",
    },
    "no_written_off": {
        "threshold": 0,
        "description": "No written-off accounts allowed",
    },
    "fraud_gate": {
        "threshold": 60,
        "description": "Fraud score must be below 60 for auto-approval",
    },
}


def _evaluate_policy(bureau_data: dict, fraud_score: float = 0, monthly_income: float = 0, requested_emi: float = 0) -> dict:
    """
    Evaluate all policy rules against bureau data.
    Returns: decision (pass/fail/refer), rule evaluations with explanations.
    """
    evaluations = []
    decision = "pass"
    
    # Rule 1: Minimum credit score
    credit_score = bureau_data.get("credit_score", 0)
    score_pass = credit_score >= POLICY_RULES["min_credit_score"]["threshold"]
    evaluations.append({
        "rule": "min_credit_score",
        "description": POLICY_RULES["min_credit_score"]["description"],
        "threshold": POLICY_RULES["min_credit_score"]["threshold"],
        "actual_value": credit_score,
        "passed": score_pass,
        "explanation": f"Credit score {credit_score} {'≥' if score_pass else '<'} {POLICY_RULES['min_credit_score']['threshold']}",
    })
    if not score_pass:
        if credit_score >= 500:
            decision = "refer"
        else:
            decision = "fail"
    
    # Rule 2: EMI-to-income ratio
    if monthly_income > 0 and requested_emi > 0:
        ratio = requested_emi / monthly_income
        ratio_pass = ratio <= POLICY_RULES["max_emi_to_income_ratio"]["threshold"]
        evaluations.append({
            "rule": "max_emi_to_income_ratio",
            "description": POLICY_RULES["max_emi_to_income_ratio"]["description"],
            "threshold": POLICY_RULES["max_emi_to_income_ratio"]["threshold"],
            "actual_value": round(ratio, 3),
            "passed": ratio_pass,
            "explanation": f"EMI/Income ratio {ratio:.2%} {'≤' if ratio_pass else '>'} {POLICY_RULES['max_emi_to_income_ratio']['threshold']:.0%}",
        })
        if not ratio_pass:
            decision = "refer" if decision != "fail" else "fail"
    
    # Rule 3: Active loans
    active_loans = bureau_data.get("active_loans", 0)
    loans_pass = active_loans <= POLICY_RULES["max_active_loans"]["threshold"]
    evaluations.append({
        "rule": "max_active_loans",
        "description": POLICY_RULES["max_active_loans"]["description"],
        "threshold": POLICY_RULES["max_active_loans"]["threshold"],
        "actual_value": active_loans,
        "passed": loans_pass,
        "explanation": f"Active loans {active_loans} {'≤' if loans_pass else '>'} {POLICY_RULES['max_active_loans']['threshold']}",
    })
    if not loans_pass:
        decision = "refer" if decision != "fail" else "fail"
    
    # Rule 4: DPD history
    dpd_history = bureau_data.get("dpd_history", [])
    max_dpd = max(dpd_history) if dpd_history else 0
    dpd_pass = max_dpd <= POLICY_RULES["max_dpd_days"]["threshold"]
    evaluations.append({
        "rule": "max_dpd_days",
        "description": POLICY_RULES["max_dpd_days"]["description"],
        "threshold": POLICY_RULES["max_dpd_days"]["threshold"],
        "actual_value": max_dpd,
        "passed": dpd_pass,
        "explanation": f"Max DPD {max_dpd} days {'≤' if dpd_pass else '>'} {POLICY_RULES['max_dpd_days']['threshold']} days",
    })
    if not dpd_pass:
        decision = "fail" if max_dpd > 180 else ("refer" if decision != "fail" else "fail")
    
    # Rule 5: Written-off accounts
    written_off = bureau_data.get("written_off_accounts", 0)
    wo_pass = written_off <= POLICY_RULES["no_written_off"]["threshold"]
    evaluations.append({
        "rule": "no_written_off",
        "description": POLICY_RULES["no_written_off"]["description"],
        "threshold": POLICY_RULES["no_written_off"]["threshold"],
        "actual_value": written_off,
        "passed": wo_pass,
        "explanation": f"Written-off accounts: {written_off} {'=' if wo_pass else '>'} 0",
    })
    if not wo_pass:
        decision = "fail"
    
    # Rule 6: Fraud gate
    fraud_pass = fraud_score < POLICY_RULES["fraud_gate"]["threshold"]
    evaluations.append({
        "rule": "fraud_gate",
        "description": POLICY_RULES["fraud_gate"]["description"],
        "threshold": POLICY_RULES["fraud_gate"]["threshold"],
        "actual_value": fraud_score,
        "passed": fraud_pass,
        "explanation": f"Fraud score {fraud_score} {'<' if fraud_pass else '≥'} {POLICY_RULES['fraud_gate']['threshold']}",
    })
    if not fraud_pass:
        decision = "fail"
    
    return {
        "decision": decision,
        "rules_evaluated": len(evaluations),
        "rules_passed": sum(1 for e in evaluations if e["passed"]),
        "evaluations": evaluations,
    }


# ──────────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────────

class BureauCheckRequest(BaseModel):
    applicant_id: Optional[str] = None
    monthly_income: Optional[float] = 0
    requested_emi: Optional[float] = 0

@router.post("/{session_id}/check")
async def check_bureau(session_id: str, req: BureauCheckRequest = None):
    """
    Call bureau mock service and apply policy rules.
    Returns credit data + policy decision with full rule explanations.
    """
    session = store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    applicant_id = (req.applicant_id if req else None) or session.get("applicant_id") or session_id[:8]
    
    # Call bureau mock service
    bureau_data = {}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{settings.BUREAU_MOCK_URL}/api/bureau/{applicant_id}")
            if resp.status_code == 200:
                bureau_data = resp.json()
            else:
                bureau_data = {
                    "credit_score": 650,
                    "active_loans": 1,
                    "dpd_history": [0],
                    "written_off_accounts": 0,
                    "error": "Bureau service returned non-200",
                }
    except httpx.TimeoutException:
        bureau_data = {
            "credit_score": 0,
            "active_loans": 0,
            "dpd_history": [],
            "written_off_accounts": 0,
            "error": "Bureau service timeout — using cached defaults",
        }
        await audit.emit(session_id, "BUREAU_TIMEOUT", "BUREAU", {"error": "timeout"})
    except Exception as e:
        bureau_data = {
            "credit_score": 650,
            "active_loans": 1,
            "dpd_history": [0],
            "written_off_accounts": 0,
            "error": str(e),
        }
    
    # Get fraud score for policy evaluation
    fraud_result = session.get("fraud_score", {})
    fraud_composite = fraud_result.get("composite_score", 0) if fraud_result else 0
    
    # Parse income from extracted fields
    monthly_income = req.monthly_income if req and req.monthly_income else 0
    if not monthly_income:
        fields = session.get("extracted_fields", {})
        income_field = fields.get("monthly_income", {})
        if isinstance(income_field, dict):
            try:
                monthly_income = float(income_field.get("value", 0))
            except (ValueError, TypeError):
                monthly_income = 0
    
    # Evaluate policy rules
    policy = _evaluate_policy(
        bureau_data,
        fraud_score=fraud_composite,
        monthly_income=monthly_income,
        requested_emi=req.requested_emi if req else 0,
    )
    
    result = {
        "session_id": session_id,
        "applicant_id": applicant_id,
        "bureau_data": bureau_data,
        "policy": policy,
        "timestamp": datetime.utcnow().isoformat(),
    }
    
    # Store
    store.update(session_id, {"bureau_result": result})
    
    # Persist
    try:
        db = await get_db()
        try:
            await db.execute(
                """INSERT INTO bureau_results
                   (session_id, applicant_id, credit_score, active_loans, dpd_history,
                    written_off, policy_decision, policy_explanation, rule_evaluations)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    session_id,
                    applicant_id,
                    bureau_data.get("credit_score"),
                    bureau_data.get("active_loans", 0),
                    json.dumps(bureau_data.get("dpd_history", [])),
                    bureau_data.get("written_off_accounts", 0),
                    policy["decision"],
                    f"{policy['rules_passed']}/{policy['rules_evaluated']} rules passed",
                    json.dumps(policy["evaluations"]),
                ),
            )
            await db.commit()
        finally:
            await db.close()
    except Exception:
        pass
    
    await audit.emit(session_id, "BUREAU_CHECKED", "BUREAU", {
        "credit_score": bureau_data.get("credit_score"),
        "decision": policy["decision"],
        "rules_passed": policy["rules_passed"],
        "rules_total": policy["rules_evaluated"],
    })
    
    return result
