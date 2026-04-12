"""
Document ingestion endpoints for PDF -> OCR -> parsed bureau fields.
"""

from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.document_pipeline import process_pdf_upload
from app.models import ParsedDocumentRecord
from app.repositories.doc_store import get_doc_record, save_doc_record

router = APIRouter(prefix="/api/docs", tags=["docs"])


@router.post("/upload", response_model=ParsedDocumentRecord, summary="Upload and parse PDF")
async def upload_pdf(file: UploadFile = File(...)):
    """Upload a PDF, run extraction+parsing, and store placeholder parsed record."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="File name is required.")

    is_pdf = file.filename.lower().endswith(".pdf") or (file.content_type == "application/pdf")
    if not is_pdf:
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    record = process_pdf_upload(pdf_bytes=pdf_bytes, filename=file.filename)
    save_doc_record(record)
    return record


@router.get("/{doc_id}", response_model=ParsedDocumentRecord, summary="Get parsed document record")
async def get_parsed_document(doc_id: str):
    """Fetch parsed placeholder record by document id."""
    record = get_doc_record(doc_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found.")
    return record

