"""
Tests for PDF parsing helpers (app/document_pipeline.py).
"""

from app.document_pipeline import parse_bureau_fields


def test_parse_bureau_fields_complete():
    raw = """
    applicant_id: DOC-001
    monthly_income: 60000
    monthly_obligations: 15000
    written_off_accounts: 0
    active_loan_count: 1
    inquiry_count_90d: 2
    on_time_pct: 98
    dpd_30_count: 0
    dpd_60_count: 0
    dpd_90_count: 0
    total_limit: 300000
    current_balance: 45000
    secured_count: 1
    unsecured_count: 1
    oldest_account_months: 72
    enquiries_last_6m: 1
    new_accounts_last_6m: 0
    dpd_last_12m: false
    """
    parsed, missing = parse_bureau_fields(raw)
    assert missing == []
    assert parsed["applicant_id"] == "DOC-001"
    assert parsed["monthly_income"] == 60000.0
    assert parsed["payment_history"]["on_time_pct"] == 98.0
    assert parsed["credit_utilization"]["total_limit"] == 300000.0
    assert parsed["new_credit"]["enquiries_last_6m"] == 1
    assert parsed["dpd_history"] == []


def test_parse_bureau_fields_missing_required():
    raw = """
    monthly_income: 60000
    monthly_obligations: 15000
    written_off_accounts: 0
    """
    parsed, missing = parse_bureau_fields(raw)
    assert parsed["monthly_income"] == 60000.0
    assert "payment_history.on_time_pct" in missing
    assert "credit_utilization.total_limit" in missing
