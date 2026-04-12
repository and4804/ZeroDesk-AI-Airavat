"""
API integration tests — full request/response against the FastAPI app.
"""

from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models import ParsedDocumentRecord

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert data["service"] == "bureau-mock"
    assert data["module"] == "M07"


# ---------------------------------------------------------------------------
# Seed listing
# ---------------------------------------------------------------------------

async def test_seed_list(client):
    resp = await client.get("/api/bureau/seed")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] >= 3
    ids = [a["applicant_id"] for a in data["applicants"]]
    assert "PRIYA-001" in ids
    assert "ROHIT-002" in ids
    assert "MEERA-003" in ids


# ---------------------------------------------------------------------------
# Bureau check — demo personas
# ---------------------------------------------------------------------------

async def test_priya_pass(client):
    """Priya Sharma — happy path → PASS."""
    resp = await client.get("/api/bureau/PRIYA-001")
    assert resp.status_code == 200
    data = resp.json()
    assert data["applicant_id"] == "PRIYA-001"
    assert data["credit_score"] == 740
    assert data["eligibility_decision"] == "PASS"
    assert data["response_source"] == "mock"
    # Check all 8 rules were evaluated
    assert len(data["rules_evaluated"]) == 8
    # FOIR sanity
    assert 0 < data["foir"] < 1


async def test_rohit_reject(client):
    """Rohit X — fraud score 82 triggers R06 → REJECT."""
    resp = await client.get("/api/bureau/ROHIT-002")
    assert resp.status_code == 200
    data = resp.json()
    assert data["applicant_id"] == "ROHIT-002"
    assert data["credit_score"] == 580
    assert data["eligibility_decision"] == "REJECT"
    # R01 should fail (580 < 650)
    r01 = next(r for r in data["rules_evaluated"] if r["rule_id"] == "R01")
    assert r01["passed"] is False
    # R06 should fail (fraud_score 82 > 60)
    r06 = next(r for r in data["rules_evaluated"] if r["rule_id"] == "R06")
    assert r06["passed"] is False
    # R07 should fail (liveness 0.45 < 0.6)
    r07 = next(r for r in data["rules_evaluated"] if r["rule_id"] == "R07")
    assert r07["passed"] is False


async def test_meera_refer(client):
    """Meera Patil — DPD in 2026 triggers R04 → REFER."""
    resp = await client.get("/api/bureau/MEERA-003")
    assert resp.status_code == 200
    data = resp.json()
    assert data["applicant_id"] == "MEERA-003"
    assert data["credit_score"] == 680
    assert data["eligibility_decision"] == "REFER"
    # R04 should fail (DPD in 2026)
    r04 = next(r for r in data["rules_evaluated"] if r["rule_id"] == "R04")
    assert r04["passed"] is False


# ---------------------------------------------------------------------------
# Bureau check — overrides
# ---------------------------------------------------------------------------

async def test_override_fraud_score(client):
    """Override fraud_score via query param — force PRIYA to REJECT."""
    resp = await client.get("/api/bureau/PRIYA-001?fraud_score=85")
    assert resp.status_code == 200
    data = resp.json()
    assert data["eligibility_decision"] == "REJECT"
    r06 = next(r for r in data["rules_evaluated"] if r["rule_id"] == "R06")
    assert r06["passed"] is False
    assert r06["value"] == 85


async def test_override_liveness(client):
    """Override liveness_avg via query param — force PRIYA to REJECT."""
    resp = await client.get("/api/bureau/PRIYA-001?liveness_avg=0.3")
    assert resp.status_code == 200
    data = resp.json()
    assert data["eligibility_decision"] == "REJECT"


async def test_override_consent(client):
    """Override consent — force PRIYA to REFER (HALT → REFER)."""
    resp = await client.get("/api/bureau/PRIYA-001?consent_detected=false")
    assert resp.status_code == 200
    data = resp.json()
    assert data["eligibility_decision"] == "REFER"


# ---------------------------------------------------------------------------
# Bureau check — not found
# ---------------------------------------------------------------------------

async def test_unknown_applicant_404(client):
    resp = await client.get("/api/bureau/NONEXISTENT-999")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Standalone mock endpoints
# ---------------------------------------------------------------------------

async def test_mock_fraud_endpoint(client):
    resp = await client.get("/api/mock/fraud-score/PRIYA-001")
    assert resp.status_code == 200
    data = resp.json()
    assert data["fraud_score"] == 12
    assert data["source"] == "standalone_mock"


async def test_mock_liveness_endpoint(client):
    resp = await client.get("/api/mock/liveness/ROHIT-002")
    assert resp.status_code == 200
    data = resp.json()
    assert data["liveness_avg"] == 0.45
    assert data["meets_threshold"] is False


async def test_mock_consent_endpoint(client):
    resp = await client.get("/api/mock/consent/PRIYA-001")
    assert resp.status_code == 200
    assert resp.json()["consent_detected"] is True


# ---------------------------------------------------------------------------
# Response schema completeness
# ---------------------------------------------------------------------------

async def test_response_has_all_bureau_table_columns(client):
    """Verify the response contains every column from the bureau_responses DDL."""
    resp = await client.get("/api/bureau/PRIYA-001")
    data = resp.json()
    required_keys = [
        "id", "applicant_id", "credit_score", "active_loan_count",
        "dpd_history", "written_off_accounts", "inquiry_count_90d",
        "foir", "eligibility_decision", "rules_evaluated",
        "response_source", "fetched_at",
    ]
    for key in required_keys:
        assert key in data, f"Missing required key: {key}"


async def test_evaluate_from_parsed_payload(client):
    payload = {
        "applicant_id": "DOC-TEST-001",
        "monthly_income": 60000,
        "monthly_obligations": 15000,
        "written_off_accounts": 0,
        "active_loan_count": 1,
        "inquiry_count_90d": 1,
        "dpd_history": [],
        "payment_history": {
            "on_time_pct": 98,
            "dpd_30_count": 0,
            "dpd_60_count": 0,
            "dpd_90_count": 0,
        },
        "credit_utilization": {
            "total_limit": 300000,
            "current_balance": 45000,
        },
        "credit_mix_age": {
            "secured_count": 1,
            "unsecured_count": 1,
            "oldest_account_months": 72,
        },
        "new_credit": {
            "enquiries_last_6m": 1,
            "new_accounts_last_6m": 0,
        },
    }

    resp = await client.post("/api/bureau/evaluate", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["applicant_id"] == "DOC-TEST-001"
    assert data["eligibility_decision"] == "PASS"
    assert 300 <= data["credit_score"] <= 900
    assert len(data["rules_evaluated"]) == 8


async def test_evaluate_missing_required_field_422(client):
    payload = {
        "monthly_income": 60000,
        "written_off_accounts": 0,
        "active_loan_count": 1,
        "dpd_history": [],
        "payment_history": {
            "on_time_pct": 98,
            "dpd_30_count": 0,
            "dpd_60_count": 0,
            "dpd_90_count": 0,
        },
        "credit_utilization": {
            "total_limit": 300000,
            "current_balance": 45000,
        },
        "credit_mix_age": {
            "secured_count": 1,
            "unsecured_count": 1,
            "oldest_account_months": 72,
        },
        "new_credit": {
            "enquiries_last_6m": 1,
            "new_accounts_last_6m": 0,
        },
    }
    resp = await client.post("/api/bureau/evaluate", json=payload)
    assert resp.status_code == 422


async def test_upload_pdf_and_fetch_parsed_record(client, monkeypatch):
    fake_record = ParsedDocumentRecord(
        doc_id="doc-test-123",
        filename="statement.pdf",
        extraction_method="native_pdf",
        parse_status="ready",
        parsed_fields={"monthly_income": 60000},
        missing_required_fields=[],
        ready_for_evaluation=True,
        errors=[],
        ocr_text="monthly_income: 60000",
        uploaded_at=datetime.now(timezone.utc),
    )

    def fake_process_pdf_upload(pdf_bytes: bytes, filename: str) -> ParsedDocumentRecord:
        assert filename == "statement.pdf"
        assert pdf_bytes
        return fake_record

    monkeypatch.setattr("app.routes.docs.process_pdf_upload", fake_process_pdf_upload)

    upload_resp = await client.post(
        "/api/docs/upload",
        files={"file": ("statement.pdf", b"%PDF-1.4 fake", "application/pdf")},
    )
    assert upload_resp.status_code == 200
    upload_data = upload_resp.json()
    assert upload_data["doc_id"] == "doc-test-123"
    assert upload_data["ready_for_evaluation"] is True

    get_resp = await client.get("/api/docs/doc-test-123")
    assert get_resp.status_code == 200
    get_data = get_resp.json()
    assert get_data["filename"] == "statement.pdf"


async def test_upload_non_pdf_rejected(client):
    resp = await client.post(
        "/api/docs/upload",
        files={"file": ("notes.txt", b"plain text", "text/plain")},
    )
    assert resp.status_code == 400
