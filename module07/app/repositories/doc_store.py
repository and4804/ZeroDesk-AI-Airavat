"""
In-memory placeholder store for parsed document records.

This acts as a temporary DB substitute for the addendum flow.
"""

from __future__ import annotations

from app.models import ParsedDocumentRecord

_DOC_STORE: dict[str, ParsedDocumentRecord] = {}


def save_doc_record(record: ParsedDocumentRecord) -> ParsedDocumentRecord:
    """Insert or replace a parsed document record."""
    _DOC_STORE[record.doc_id] = record
    return record


def get_doc_record(doc_id: str) -> ParsedDocumentRecord | None:
    """Fetch a parsed document record by id."""
    return _DOC_STORE.get(doc_id)

