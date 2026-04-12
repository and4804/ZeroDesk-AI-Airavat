"""
M07 Pydantic models — aligned with the bureau_responses table DDL.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------

class DpdEntry(BaseModel):
    """Single DPD (Days Past Due) history record."""
    days: int = Field(..., description="DPD bucket — 30, 60, or 90")
    count: int = Field(..., description="Number of occurrences")
    year: int = Field(..., description="Calendar year of the DPD events")


class RuleEvaluation(BaseModel):
    """Result of evaluating one eligibility rule."""
    rule_id: str = Field(..., description="Rule identifier e.g. R01")
    rule_name: str = Field("", description="Human-readable rule name")
    passed: bool = Field(..., description="True if applicant passed this rule")
    value: Any = Field(None, description="Actual value that was evaluated")
    threshold: Any = Field(None, description="Threshold the value was compared against")
    action_on_fail: str = Field("", description="REJECT / REFER / HALT — action if rule fails")


# ---------------------------------------------------------------------------
# Bureau response — maps to bureau_responses table
# ---------------------------------------------------------------------------

class BureauResponse(BaseModel):
    """
    Full mock bureau response.

    Every field maps 1:1 to a column in the ``bureau_responses`` Supabase
    table defined in the project DDL.
    """
    id: UUID = Field(default_factory=uuid4)
    session_id: Optional[UUID] = Field(
        None,
        description="Session UUID — optional, set when called from orchestrator",
    )
    applicant_id: str
    credit_score: int = Field(..., ge=300, le=900, description="Simulated CIBIL score")
    active_loan_count: int = Field(..., ge=0)
    dpd_history: list[DpdEntry] = Field(default_factory=list)
    written_off_accounts: int = Field(0, ge=0)
    inquiry_count_90d: int = Field(0, ge=0, description="Hard inquiries in last 90 days")
    foir: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Fixed Obligation to Income Ratio",
    )
    eligibility_decision: str = Field(
        ...,
        pattern="^(PASS|REFER|REJECT)$",
        description="Final eligibility decision",
    )
    rules_evaluated: list[RuleEvaluation] = Field(default_factory=list)
    response_source: str = Field("mock", description="mock | cached | live")
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = {"json_schema_extra": {"example": {
        "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "session_id": None,
        "applicant_id": "PRIYA-001",
        "credit_score": 740,
        "active_loan_count": 1,
        "dpd_history": [],
        "written_off_accounts": 0,
        "inquiry_count_90d": 1,
        "foir": 0.25,
        "eligibility_decision": "PASS",
        "rules_evaluated": [
            {"rule_id": "R01", "rule_name": "Minimum Credit Score",
             "passed": True, "value": 740, "threshold": 650, "action_on_fail": "REJECT"}
        ],
        "response_source": "mock",
        "fetched_at": "2026-04-11T10:30:00Z",
    }}}


# ---------------------------------------------------------------------------
# Scoring sub-models (internal, not persisted)
# ---------------------------------------------------------------------------

class PaymentHistory(BaseModel):
    on_time_pct: float
    dpd_30_count: int = 0
    dpd_60_count: int = 0
    dpd_90_count: int = 0


class CreditUtilization(BaseModel):
    total_limit: float
    current_balance: float


class CreditMixAge(BaseModel):
    secured_count: int = 0
    unsecured_count: int = 0
    oldest_account_months: int = 0


class NewCredit(BaseModel):
    enquiries_last_6m: int = 0
    new_accounts_last_6m: int = 0


# ---------------------------------------------------------------------------
# Addendum models — PDF parse + POST evaluation flow
# ---------------------------------------------------------------------------

class ParsedPaymentHistory(BaseModel):
    on_time_pct: float
    dpd_30_count: int
    dpd_60_count: int
    dpd_90_count: int


class ParsedCreditUtilization(BaseModel):
    total_limit: float
    current_balance: float


class ParsedCreditMixAge(BaseModel):
    secured_count: int
    unsecured_count: int
    oldest_account_months: int


class ParsedNewCredit(BaseModel):
    enquiries_last_6m: int
    new_accounts_last_6m: int


class BureauEvaluateRequest(BaseModel):
    """Parsed-input evaluation request for POST /api/bureau/evaluate."""

    applicant_id: Optional[str] = None
    source_doc_id: Optional[str] = None
    session_id: Optional[UUID] = None

    monthly_income: float = Field(..., ge=0.0)
    monthly_obligations: float = Field(..., ge=0.0)
    written_off_accounts: int = Field(..., ge=0)
    active_loan_count: int = Field(..., ge=0)
    inquiry_count_90d: int = Field(0, ge=0)
    dpd_history: list[DpdEntry] = Field(default_factory=list)

    payment_history: ParsedPaymentHistory
    credit_utilization: ParsedCreditUtilization
    credit_mix_age: ParsedCreditMixAge
    new_credit: ParsedNewCredit

    fraud_score: Optional[int] = Field(None, ge=0, le=100)
    liveness_avg: Optional[float] = Field(None, ge=0.0, le=1.0)
    consent_detected: Optional[bool] = None


class BureauEvaluateResponse(BureauResponse):
    """Bureau response with source-document trace metadata."""

    source_doc_id: Optional[str] = None
    parse_status: Optional[str] = None


class ParsedDocumentRecord(BaseModel):
    """Placeholder DB record for uploaded/parsed PDFs."""

    doc_id: str
    filename: str
    extraction_method: str
    parse_status: str
    parsed_fields: dict[str, Any]
    missing_required_fields: list[str] = Field(default_factory=list)
    ready_for_evaluation: bool = False
    errors: list[str] = Field(default_factory=list)
    ocr_text: str = ""
    uploaded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
