"""
PDF ingestion pipeline: extract text (native/OCR) and parse bureau fields.
"""

from __future__ import annotations

import io
import re
from uuid import uuid4

from fastapi import HTTPException

from app.config import CURRENT_YEAR
from app.models import ParsedDocumentRecord


def _normalise_key(raw_key: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", raw_key.lower()).strip("_")


def _to_number(raw_value: str, as_int: bool = False) -> float | int | None:
    cleaned = raw_value.strip().replace(",", "")
    cleaned = cleaned.replace("%", "")
    match = re.search(r"[-+]?\d*\.?\d+", cleaned)
    if not match:
        return None
    value = float(match.group(0))
    if as_int:
        return int(round(value))
    return value


def _to_bool(raw_value: str) -> bool | None:
    cleaned = raw_value.strip().lower()
    if cleaned in {"true", "yes", "y", "1", "present", "detected"}:
        return True
    if cleaned in {"false", "no", "n", "0", "absent", "not_detected", "not detected"}:
        return False
    return None


def extract_text_from_pdf(pdf_bytes: bytes) -> tuple[str, str]:
    """
    Return extracted text and method: native_pdf | ocr.
    """
    native_text = ""
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(pdf_bytes))
        native_text = "\n".join((page.extract_text() or "") for page in reader.pages).strip()
    except Exception:
        native_text = ""

    if len(native_text) >= 40:
        return native_text, "native_pdf"

    try:
        from pdf2image import convert_from_bytes
        import pytesseract
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                "OCR dependencies unavailable. Install pdf2image, pytesseract, and system "
                "packages poppler + tesseract."
            ),
        ) from exc

    try:
        images = convert_from_bytes(pdf_bytes)
        ocr_text = "\n".join((pytesseract.image_to_string(img) or "") for img in images).strip()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"OCR failed: {exc}") from exc

    if not ocr_text:
        raise HTTPException(status_code=422, detail="Could not extract text from uploaded PDF.")
    return ocr_text, "ocr"


def parse_bureau_fields(raw_text: str) -> tuple[dict, list[str]]:
    """
    Parse required bureau/scoring fields from extracted text.

    Expected format is key-value friendly text, e.g.:
      monthly_income: 60000
      on_time_pct: 98
      consent_detected: true
    """
    kv: dict[str, str] = {}
    for line in raw_text.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
        elif "=" in line:
            k, v = line.split("=", 1)
        else:
            continue
        norm_key = _normalise_key(k)
        norm_value = v.strip()
        if norm_key and norm_value:
            kv[norm_key] = norm_value

    def pick(*aliases: str) -> str | None:
        for alias in aliases:
            if alias in kv:
                return kv[alias]
        return None

    monthly_income = _to_number(pick("monthly_income", "income_per_month", "income_monthly") or "")
    monthly_obligations = _to_number(
        pick("monthly_obligations", "monthly_emi", "monthly_commitments") or ""
    )
    written_off_accounts = _to_number(
        pick("written_off_accounts", "writeoff_accounts", "written_off_count") or "",
        as_int=True,
    )
    active_loan_count = _to_number(pick("active_loan_count", "active_loans") or "", as_int=True)
    inquiry_count_90d = _to_number(
        pick("inquiry_count_90d", "hard_inquiries_90d", "inquiries_90d") or "",
        as_int=True,
    )

    on_time_pct = _to_number(pick("on_time_pct", "payment_on_time_pct") or "")
    dpd_30_count = _to_number(pick("dpd_30_count") or "", as_int=True)
    dpd_60_count = _to_number(pick("dpd_60_count") or "", as_int=True)
    dpd_90_count = _to_number(pick("dpd_90_count") or "", as_int=True)

    total_limit = _to_number(pick("total_limit", "credit_limit_total") or "")
    current_balance = _to_number(pick("current_balance", "credit_balance_current") or "")

    secured_count = _to_number(pick("secured_count", "secured_accounts") or "", as_int=True)
    unsecured_count = _to_number(pick("unsecured_count", "unsecured_accounts") or "", as_int=True)
    oldest_account_months = _to_number(
        pick("oldest_account_months", "oldest_account_age_months") or "",
        as_int=True,
    )

    enquiries_last_6m = _to_number(
        pick("enquiries_last_6m", "enquiries_6m", "inquiries_last_6m") or "",
        as_int=True,
    )
    new_accounts_last_6m = _to_number(
        pick("new_accounts_last_6m", "new_accounts_6m") or "",
        as_int=True,
    )

    dpd_last_12m = _to_bool(pick("dpd_last_12m", "recent_dpd") or "")
    consent_detected = _to_bool(pick("consent_detected", "consent") or "")
    fraud_score = _to_number(pick("fraud_score") or "", as_int=True)
    liveness_avg = _to_number(pick("liveness_avg", "liveness") or "")
    applicant_id = pick("applicant_id", "customer_id")

    dpd_history = []
    if dpd_last_12m is True:
        dpd_history = [{"days": 30, "count": 1, "year": CURRENT_YEAR}]
    elif dpd_last_12m is False:
        dpd_history = []

    parsed_fields = {
        "applicant_id": applicant_id,
        "monthly_income": monthly_income,
        "monthly_obligations": monthly_obligations,
        "written_off_accounts": written_off_accounts,
        "active_loan_count": active_loan_count,
        "inquiry_count_90d": inquiry_count_90d or 0,
        "dpd_history": dpd_history,
        "payment_history": {
            "on_time_pct": on_time_pct,
            "dpd_30_count": dpd_30_count,
            "dpd_60_count": dpd_60_count,
            "dpd_90_count": dpd_90_count,
        },
        "credit_utilization": {
            "total_limit": total_limit,
            "current_balance": current_balance,
        },
        "credit_mix_age": {
            "secured_count": secured_count,
            "unsecured_count": unsecured_count,
            "oldest_account_months": oldest_account_months,
        },
        "new_credit": {
            "enquiries_last_6m": enquiries_last_6m,
            "new_accounts_last_6m": new_accounts_last_6m,
        },
        "fraud_score": fraud_score,
        "liveness_avg": liveness_avg,
        "consent_detected": consent_detected,
    }

    required_paths = [
        "monthly_income",
        "monthly_obligations",
        "written_off_accounts",
        "active_loan_count",
        "payment_history.on_time_pct",
        "payment_history.dpd_30_count",
        "payment_history.dpd_60_count",
        "payment_history.dpd_90_count",
        "credit_utilization.total_limit",
        "credit_utilization.current_balance",
        "credit_mix_age.secured_count",
        "credit_mix_age.unsecured_count",
        "credit_mix_age.oldest_account_months",
        "new_credit.enquiries_last_6m",
        "new_credit.new_accounts_last_6m",
    ]

    def get_path_value(payload: dict, path: str):
        current = payload
        for part in path.split("."):
            if not isinstance(current, dict):
                return None
            current = current.get(part)
        return current

    missing_required = [path for path in required_paths if get_path_value(parsed_fields, path) is None]
    return parsed_fields, missing_required


def process_pdf_upload(pdf_bytes: bytes, filename: str) -> ParsedDocumentRecord:
    """Build a parsed document record from uploaded PDF bytes."""
    raw_text, extraction_method = extract_text_from_pdf(pdf_bytes)
    parsed_fields, missing_required = parse_bureau_fields(raw_text)
    parse_status = "ready" if not missing_required else "incomplete"

    return ParsedDocumentRecord(
        doc_id=str(uuid4()),
        filename=filename,
        extraction_method=extraction_method,
        parse_status=parse_status,
        parsed_fields=parsed_fields,
        missing_required_fields=missing_required,
        ready_for_evaluation=parse_status == "ready",
        ocr_text=raw_text,
    )

