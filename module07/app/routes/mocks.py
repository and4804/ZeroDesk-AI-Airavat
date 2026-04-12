"""
Standalone mock endpoints for cross-module signals.

These allow isolated testing of fraud_score (M06), liveness_avg (M04),
and consent_detected (M03) without running those services.
"""

from fastapi import APIRouter

from app.standalone_mocks import (
    get_consent_detected,
    get_fraud_score,
    get_liveness_avg,
)

router = APIRouter(prefix="/api/mock", tags=["standalone-mocks"])


@router.get("/fraud-score/{applicant_id}")
async def mock_fraud_score(applicant_id: str):
    """Return a deterministic mock fraud score (0–100) for the given applicant."""
    score = get_fraud_score(applicant_id)
    return {
        "applicant_id": applicant_id,
        "fraud_score": score,
        "risk_level": "low" if score <= 30 else ("medium" if score <= 60 else "high"),
        "source": "standalone_mock",
    }


@router.get("/liveness/{applicant_id}")
async def mock_liveness(applicant_id: str):
    """Return a deterministic mock liveness average (0.0–1.0) for the given applicant."""
    avg = get_liveness_avg(applicant_id)
    return {
        "applicant_id": applicant_id,
        "liveness_avg": avg,
        "meets_threshold": avg >= 0.6,
        "source": "standalone_mock",
    }


@router.get("/consent/{applicant_id}")
async def mock_consent(applicant_id: str):
    """Return a deterministic mock consent flag for the given applicant."""
    detected = get_consent_detected(applicant_id)
    return {
        "applicant_id": applicant_id,
        "consent_detected": detected,
        "source": "standalone_mock",
    }
