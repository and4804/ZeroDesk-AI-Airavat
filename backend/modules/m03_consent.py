"""
M03 — Verbal Consent Capture & Auditable Consent Trail
Detects consent phrases, timestamps + SHA-256 hashes transcript segments,
produces tamper-evident signed artifacts for regulatory use.
"""

import hashlib
import hmac
import json
import re
from datetime import datetime
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from config import settings
from database import get_db
from session_store import store
from events import audit

router = APIRouter(prefix="/api/consent", tags=["M03 - Consent"])

# ──────────────────────────────────────────────────────────────────
# Consent phrase patterns
# ──────────────────────────────────────────────────────────────────

CONSENT_PHRASES = [
    r"\bi\s+agree\b",
    r"\byes\s*,?\s*i\s+consent\b",
    r"\bi\s+consent\b",
    r"\bi\s+accept\b",
    r"\byes\s*,?\s*i\s+agree\b",
    r"\bi\s+give\s+(my\s+)?consent\b",
    r"\bi\s+authorize\b",
    r"\byes\s*,?\s*please\s+proceed\b",
    r"\bgo\s+ahead\b",
    r"\bthat'?s?\s+fine\b",
    r"\bok(ay)?\s*,?\s*i\s+agree\b",
]

OPT_OUT_PHRASES = [
    r"\bi\s+do\s+not\s+(consent|agree)\b",
    r"\bi\s+don'?t\s+(consent|agree)\b",
    r"\bi\s+refuse\b",
    r"\bi\s+decline\b",
    r"\bno\s*,?\s*i\s+don'?t\s+(want|agree)\b",
    r"\bstop\s+the\s+(process|call)\b",
]


def _detect_consent(text: str) -> dict:
    """Detect consent or opt-out phrases in text."""
    text_lower = text.lower().strip()
    
    # Check opt-out first (takes priority)
    for pattern in OPT_OUT_PHRASES:
        match = re.search(pattern, text_lower)
        if match:
            return {
                "detected": True,
                "is_consent": False,
                "phrase": match.group(),
                "type": "opt_out",
            }
    
    # Check consent phrases
    for pattern in CONSENT_PHRASES:
        match = re.search(pattern, text_lower)
        if match:
            return {
                "detected": True,
                "is_consent": True,
                "phrase": match.group(),
                "type": "verbal_consent",
            }
    
    return {"detected": False, "is_consent": False, "phrase": None, "type": None}


def _hash_segment(text: str) -> str:
    """SHA-256 hash of a transcript segment."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sign_artifact(data: dict) -> str:
    """HMAC-SHA256 sign an artifact using JWT secret."""
    payload = json.dumps(data, sort_keys=True)
    return hmac.new(
        settings.JWT_SECRET.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


# ──────────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────────

class ConsentCheckRequest(BaseModel):
    transcript_segment: Optional[str] = None

@router.post("/{session_id}/check")
async def check_consent(session_id: str, req: ConsentCheckRequest = None):
    """
    Check transcript for consent phrases.
    If transcript_segment is provided, checks that specific text.
    Otherwise, checks the full session transcript.
    """
    session = store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Get text to check
    if req and req.transcript_segment:
        text = req.transcript_segment
    else:
        text = store.get_full_transcript(session_id)
    
    if not text:
        return {"session_id": session_id, "consent_detected": False, "message": "No transcript available"}
    
    result = _detect_consent(text)
    
    if result["detected"]:
        timestamp = datetime.utcnow().isoformat()
        segment_hash = _hash_segment(text)
        
        consent_record = {
            "session_id": session_id,
            "consent_type": result["type"],
            "phrase_detected": result["phrase"],
            "transcript_segment": text[:500],  # Store first 500 chars
            "segment_hash": segment_hash,
            "is_consent": result["is_consent"],
            "timestamp": timestamp,
        }
        
        # Store in memory
        store.update(session_id, {"consent": consent_record})
        
        # Persist to DB
        db = await get_db()
        try:
            await db.execute(
                """INSERT INTO consent_records 
                   (session_id, consent_type, phrase_detected, transcript_segment, segment_hash, is_consent)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    session_id,
                    result["type"],
                    result["phrase"],
                    text[:500],
                    segment_hash,
                    1 if result["is_consent"] else 0,
                ),
            )
            await db.commit()
        finally:
            await db.close()
        
        # Audit event
        event_type = "CONSENT_CAPTURED" if result["is_consent"] else "OPT_OUT_DETECTED"
        await audit.emit(session_id, event_type, "CONSENT", {
            "phrase": result["phrase"],
            "hash": segment_hash[:16] + "...",
            "is_consent": result["is_consent"],
        })
        
        return {
            "session_id": session_id,
            "consent_detected": True,
            "is_consent": result["is_consent"],
            "record": consent_record,
        }
    
    return {
        "session_id": session_id,
        "consent_detected": False,
        "message": "No consent or opt-out phrase detected",
    }


@router.get("/{session_id}")
async def get_consent(session_id: str):
    """Get consent record for a session."""
    session = store.get(session_id)
    if session and session.get("consent"):
        return session["consent"]
    
    # Try DB
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM consent_records WHERE session_id = ? ORDER BY timestamp DESC LIMIT 1",
            (session_id,),
        )
        row = await cursor.fetchone()
        if row:
            return dict(row)
    finally:
        await db.close()
    
    raise HTTPException(status_code=404, detail="No consent record found")


@router.get("/{session_id}/export")
async def export_consent_artifact(session_id: str):
    """
    Export a signed, tamper-evident consent artifact for regulatory use.
    Contains: session_id, consent phrase, transcript hash, timestamp, HMAC signature.
    """
    # Get consent record
    session = store.get(session_id)
    consent = session.get("consent") if session else None
    
    if not consent:
        db = await get_db()
        try:
            cursor = await db.execute(
                "SELECT * FROM consent_records WHERE session_id = ? ORDER BY timestamp DESC LIMIT 1",
                (session_id,),
            )
            row = await cursor.fetchone()
            if row:
                consent = dict(row)
        finally:
            await db.close()
    
    if not consent:
        raise HTTPException(status_code=404, detail="No consent record found for this session")
    
    # Build artifact
    artifact = {
        "artifact_type": "consent_record",
        "version": "1.0",
        "session_id": session_id,
        "consent_type": consent.get("consent_type", "verbal"),
        "phrase_detected": consent.get("phrase_detected"),
        "transcript_segment_hash": consent.get("segment_hash"),
        "is_consent": consent.get("is_consent", True),
        "timestamp": consent.get("timestamp", datetime.utcnow().isoformat()),
        "generated_at": datetime.utcnow().isoformat(),
    }
    
    # Sign the artifact
    signature = _sign_artifact(artifact)
    artifact["hmac_signature"] = signature
    artifact["signature_algorithm"] = "HMAC-SHA256"
    
    await audit.emit(session_id, "CONSENT_ARTIFACT_EXPORTED", "CONSENT", {
        "signature": signature[:16] + "...",
    })
    
    return artifact
