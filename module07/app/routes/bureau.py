"""
Bureau check endpoint — primary M07 API.

GET /api/bureau/{applicant_id}

Returns a mock bureau response matching the bureau_responses table schema.
Cross-module signals can be overridden via query parameters; otherwise
standalone mock defaults are used.
"""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from app.config import get_seed_profile, load_seed_data
from app.decision import derive_decision
from app.models import (
    BureauEvaluateRequest,
    BureauEvaluateResponse,
    BureauResponse,
    CreditMixAge,
    CreditUtilization,
    DpdEntry,
    NewCredit,
    PaymentHistory,
)
from app.repositories.doc_store import get_doc_record
from app.rules_engine import evaluate_rules
from app.scoring import calculate_credit_score
from app.standalone_mocks import (
    get_consent_detected,
    get_fraud_score,
    get_liveness_avg,
)

router = APIRouter(prefix="/api/bureau", tags=["bureau"])


@router.get("/seed", summary="List all seed applicant IDs")
async def list_seed_profiles():
    """Return a list of all available seed applicant IDs for testing."""
    profiles = load_seed_data()
    return {
        "count": len(profiles),
        "applicants": [
            {"applicant_id": p["applicant_id"], "name": p["name"]}
            for p in profiles
        ],
    }


@router.get(
    "/{applicant_id}",
    response_model=BureauResponse,
    summary="Mock bureau check for an applicant",
)
async def bureau_check(
    applicant_id: str,
    session_id: Optional[UUID] = Query(None, description="Session UUID from orchestrator"),
    fraud_score: Optional[int] = Query(None, ge=0, le=100, description="Override M06 fraud score"),
    liveness_avg: Optional[float] = Query(None, ge=0.0, le=1.0, description="Override M04 liveness avg"),
    consent_detected: Optional[bool] = Query(None, description="Override M03 consent flag"),
):
    """
    Perform a mock bureau credit check and eligibility evaluation.

    1. Look up the applicant in ``bureau_seed.json``
    2. Compute or use preset ``credit_score``
    3. Calculate ``foir`` (Fixed Obligation to Income Ratio)
    4. Resolve cross-module signals (overrides → standalone mocks → defaults)
    5. Run R01–R08 rules engine
    6. Derive eligibility decision
    7. Return response conforming to ``bureau_responses`` table schema
    """
    # ── 1. Seed lookup ────────────────────────────────────────────────
    profile = get_seed_profile(applicant_id)
    if profile is None:
        raise HTTPException(
            status_code=404,
            detail=f"Applicant '{applicant_id}' not found in seed data. "
                   f"Use GET /api/bureau/seed to list available IDs.",
        )

    # ── 2. Credit score ───────────────────────────────────────────────
    preset_score = profile.get("credit_score")
    if preset_score is not None:
        credit_score = preset_score
    else:
        credit_score = calculate_credit_score(
            payment_history=PaymentHistory(**profile["payment_history"]),
            credit_utilization=CreditUtilization(**profile["credit_utilization"]),
            credit_mix_age=CreditMixAge(**profile["credit_mix_age"]),
            new_credit=NewCredit(**profile["new_credit"]),
        )

    # ── 3. FOIR ───────────────────────────────────────────────────────
    monthly_income = profile.get("monthly_income", 1)
    monthly_obligations = profile.get("monthly_obligations", 0)
    foir = round(monthly_obligations / monthly_income, 4) if monthly_income > 0 else 1.0

    # ── 4. Cross-module signals (override → mock → default) ──────────
    resolved_fraud = fraud_score if fraud_score is not None else get_fraud_score(applicant_id)
    resolved_liveness = liveness_avg if liveness_avg is not None else get_liveness_avg(applicant_id)
    resolved_consent = consent_detected if consent_detected is not None else get_consent_detected(applicant_id)

    # ── 5. DPD history ────────────────────────────────────────────────
    dpd_entries = [DpdEntry(**d) for d in profile.get("dpd_history", [])]

    # ── 6. Rules engine ───────────────────────────────────────────────
    rules_results = evaluate_rules(
        credit_score=credit_score,
        written_off_accounts=profile.get("written_off_accounts", 0),
        foir=foir,
        dpd_history=dpd_entries,
        active_loan_count=profile.get("active_loan_count", 0),
        fraud_score=resolved_fraud,
        liveness_avg=resolved_liveness,
        consent_detected=resolved_consent,
    )

    # ── 7. Decision ───────────────────────────────────────────────────
    decision = derive_decision(rules_results)

    # ── 8. Build response ─────────────────────────────────────────────
    return BureauResponse(
        session_id=session_id,
        applicant_id=profile["applicant_id"],
        credit_score=credit_score,
        active_loan_count=profile.get("active_loan_count", 0),
        dpd_history=dpd_entries,
        written_off_accounts=profile.get("written_off_accounts", 0),
        inquiry_count_90d=profile.get("inquiry_count_90d", 0),
        foir=foir,
        eligibility_decision=decision,
        rules_evaluated=rules_results,
        response_source="mock",
    )


@router.post(
    "/evaluate",
    response_model=BureauEvaluateResponse,
    summary="Evaluate bureau eligibility using parsed payload",
)
async def evaluate_from_parsed_payload(payload: BureauEvaluateRequest):
    """
    Evaluate rules/decision using parsed bureau inputs from uploaded docs.

    `credit_score` is derived inside M07 from scoring component blocks.
    """
    if payload.source_doc_id:
        doc_record = get_doc_record(payload.source_doc_id)
        if doc_record is None:
            raise HTTPException(status_code=404, detail=f"Document '{payload.source_doc_id}' not found.")
    else:
        doc_record = None

    credit_score = calculate_credit_score(
        payment_history=PaymentHistory(**payload.payment_history.model_dump()),
        credit_utilization=CreditUtilization(**payload.credit_utilization.model_dump()),
        credit_mix_age=CreditMixAge(**payload.credit_mix_age.model_dump()),
        new_credit=NewCredit(**payload.new_credit.model_dump()),
    )

    foir = round(payload.monthly_obligations / payload.monthly_income, 4) if payload.monthly_income > 0 else 1.0

    resolved_applicant_id = payload.applicant_id or (
        f"DOC-{payload.source_doc_id[:8]}" if payload.source_doc_id else "DOC-UPLOAD"
    )
    resolved_fraud = payload.fraud_score if payload.fraud_score is not None else get_fraud_score(resolved_applicant_id)
    resolved_liveness = (
        payload.liveness_avg if payload.liveness_avg is not None else get_liveness_avg(resolved_applicant_id)
    )
    resolved_consent = (
        payload.consent_detected
        if payload.consent_detected is not None
        else get_consent_detected(resolved_applicant_id)
    )

    rules_results = evaluate_rules(
        credit_score=credit_score,
        written_off_accounts=payload.written_off_accounts,
        foir=foir,
        dpd_history=payload.dpd_history,
        active_loan_count=payload.active_loan_count,
        fraud_score=resolved_fraud,
        liveness_avg=resolved_liveness,
        consent_detected=resolved_consent,
    )

    decision = derive_decision(rules_results)

    return BureauEvaluateResponse(
        session_id=payload.session_id,
        applicant_id=resolved_applicant_id,
        credit_score=credit_score,
        active_loan_count=payload.active_loan_count,
        dpd_history=payload.dpd_history,
        written_off_accounts=payload.written_off_accounts,
        inquiry_count_90d=payload.inquiry_count_90d,
        foir=foir,
        eligibility_decision=decision,
        rules_evaluated=rules_results,
        response_source="mock",
        source_doc_id=payload.source_doc_id,
        parse_status=doc_record.parse_status if doc_record else None,
    )
