"""
M02 — Real-Time Speech-to-Text & Data Extraction
Transcribes live audio via faster-whisper, extracts structured fields using Groq LLM.
"""

import json
import base64
import tempfile
import os
from datetime import datetime
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from typing import Optional

from config import settings
from database import get_db
from session_store import store
from events import audit

router = APIRouter(prefix="/api/stt", tags=["M02 - STT"])

# Lazy-load whisper model
_whisper_model = None


def _get_whisper():
    global _whisper_model
    if _whisper_model is None:
        try:
            from faster_whisper import WhisperModel
            _whisper_model = WhisperModel(
                settings.WHISPER_MODEL,
                device=settings.WHISPER_DEVICE,
                compute_type=settings.WHISPER_COMPUTE_TYPE,
            )
            print("[OK] Whisper model loaded")
        except Exception as e:
            print(f"[WARN] Whisper load failed: {e}. Using mock STT.")
            _whisper_model = "mock"
    return _whisper_model


async def _extract_fields_llm(transcript: str, session_id: str) -> dict:
    """Use Groq LLM to extract structured application fields from transcript."""
    if not settings.has_groq_key:
        # Mock extraction for demo without API key
        return {
            "fields": {
                "name": {"value": "Demo Applicant", "confidence": 0.5},
                "age": {"value": "30", "confidence": 0.5},
                "employment_type": {"value": "salaried", "confidence": 0.5},
                "monthly_income": {"value": "50000", "confidence": 0.5},
                "loan_purpose": {"value": "home improvement", "confidence": 0.5},
                "requested_amount": {"value": "500000", "confidence": 0.5},
            },
            "model": "mock",
        }
    
    try:
        from groq import Groq
        client = Groq(api_key=settings.GROQ_API_KEY)
        
        prompt = f"""You are a data extraction agent for a loan application. 
Extract the following fields from this conversation transcript. 
For each field, provide the extracted value and a confidence score (0.0 to 1.0).
If a field is not mentioned, set value to null and confidence to 0.0.

Fields to extract:
- name: Full name of the applicant
- age: Age of the applicant (number)
- employment_type: Type of employment (salaried/self-employed/business/unemployed)
- monthly_income: Monthly income in INR (number only)
- loan_purpose: Purpose of the loan
- requested_amount: Requested loan amount in INR (number only)
- city: City of residence
- employer_name: Name of employer (if salaried)

Transcript:
\"\"\"{transcript}\"\"\"

Respond ONLY with valid JSON in this exact format:
{{
  "name": {{"value": "...", "confidence": 0.9}},
  "age": {{"value": "30", "confidence": 0.8}},
  "employment_type": {{"value": "salaried", "confidence": 0.9}},
  "monthly_income": {{"value": "50000", "confidence": 0.7}},
  "loan_purpose": {{"value": "...", "confidence": 0.8}},
  "requested_amount": {{"value": "500000", "confidence": 0.85}},
  "city": {{"value": "...", "confidence": 0.6}},
  "employer_name": {{"value": "...", "confidence": 0.5}}
}}"""

        response = client.chat.completions.create(
            model=settings.GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=512,
        )
        
        raw = response.choices[0].message.content.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
        
        fields = json.loads(raw)
        return {"fields": fields, "model": settings.GROQ_MODEL}
        
    except Exception as e:
        print(f"[WARN] LLM extraction failed: {e}")
        return {"fields": {}, "model": "error", "error": str(e)}


# ──────────────────────────────────────────────────────────────────
# WebSocket — Real-time audio transcription
# ──────────────────────────────────────────────────────────────────

@router.websocket("/ws/{session_id}")
async def websocket_stt(websocket: WebSocket, session_id: str):
    """
    WebSocket endpoint for real-time audio transcription.
    Client sends: base64-encoded audio chunks (WebM/Opus or WAV)
    Server sends: JSON with transcribed text segments
    """
    await websocket.accept()
    
    session = store.get(session_id)
    if not session:
        await websocket.send_json({"error": "Session not found"})
        await websocket.close()
        return
    
    await audit.emit(session_id, "STT_STREAM_STARTED", "STT", {})
    segment_index = 0
    
    model = _get_whisper()
    
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            
            if msg.get("type") == "audio_chunk":
                audio_b64 = msg["data"]
                audio_bytes = base64.b64decode(audio_b64)
                
                text = ""
                confidence = 0.0
                
                if model == "mock" or model is None:
                    # Mock transcription for demo
                    text = f"[Mock transcript segment {segment_index}]"
                    confidence = 0.95
                else:
                    # Real transcription with faster-whisper
                    try:
                        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                            tmp.write(audio_bytes)
                            tmp_path = tmp.name
                        
                        segments_iter, info = model.transcribe(
                            tmp_path,
                            beam_size=1,
                            language="en",
                            vad_filter=True,
                        )
                        
                        parts = []
                        for seg in segments_iter:
                            parts.append(seg.text)
                            confidence = max(confidence, seg.avg_logprob)
                        
                        text = " ".join(parts).strip()
                        os.unlink(tmp_path)
                        
                        # Convert log prob to 0-1 confidence
                        import math
                        confidence = math.exp(confidence) if confidence < 0 else confidence
                        
                    except Exception as e:
                        text = ""
                        print(f"[WARN] Whisper error: {e}")
                
                if text:
                    segment = {
                        "index": segment_index,
                        "text": text,
                        "confidence": round(confidence, 3),
                        "timestamp": datetime.utcnow().isoformat(),
                    }
                    
                    # Store in memory
                    store.append_transcript(session_id, segment)
                    
                    # Persist to DB
                    try:
                        db = await get_db()
                        try:
                            await db.execute(
                                """INSERT INTO transcripts (session_id, segment_index, text, confidence)
                                   VALUES (?, ?, ?, ?)""",
                                (session_id, segment_index, text, confidence),
                            )
                            await db.commit()
                        finally:
                            await db.close()
                    except Exception:
                        pass
                    
                    # Send back to client
                    await websocket.send_json({
                        "type": "transcript",
                        "segment": segment,
                    })
                    
                    segment_index += 1
            
            elif msg.get("type") == "end":
                break
                
    except WebSocketDisconnect:
        pass
    finally:
        await audit.emit(session_id, "STT_STREAM_ENDED", "STT", {
            "total_segments": segment_index,
        })


# ──────────────────────────────────────────────────────────────────
# REST Endpoints
# ──────────────────────────────────────────────────────────────────

@router.get("/{session_id}/transcript")
async def get_transcript(session_id: str):
    """Get full transcript for a session."""
    # Try in-memory first
    session = store.get(session_id)
    if session and session.get("transcript"):
        return {
            "session_id": session_id,
            "segments": session["transcript"],
            "full_text": store.get_full_transcript(session_id),
        }
    
    # Fall back to DB
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM transcripts WHERE session_id = ? ORDER BY segment_index",
            (session_id,),
        )
        rows = await cursor.fetchall()
        segments = [dict(row) for row in rows]
        full_text = " ".join(r["text"] for r in segments)
        return {"session_id": session_id, "segments": segments, "full_text": full_text}
    finally:
        await db.close()


@router.post("/{session_id}/extract")
async def extract_fields(session_id: str):
    """Extract structured application fields from transcript using LLM."""
    transcript = store.get_full_transcript(session_id)
    if not transcript:
        # Try DB
        db = await get_db()
        try:
            cursor = await db.execute(
                "SELECT text FROM transcripts WHERE session_id = ? ORDER BY segment_index",
                (session_id,),
            )
            rows = await cursor.fetchall()
            transcript = " ".join(row["text"] for row in rows)
        finally:
            await db.close()
    
    if not transcript:
        raise HTTPException(status_code=404, detail="No transcript found")
    
    result = await _extract_fields_llm(transcript, session_id)
    
    # Store extracted fields
    if result.get("fields"):
        store.update(session_id, {"extracted_fields": result["fields"]})
        
        db = await get_db()
        try:
            for field_name, field_data in result["fields"].items():
                if isinstance(field_data, dict):
                    await db.execute(
                        """INSERT INTO extracted_fields (session_id, field_name, field_value, confidence)
                           VALUES (?, ?, ?, ?)""",
                        (session_id, field_name, field_data.get("value"), field_data.get("confidence", 0)),
                    )
            await db.commit()
        finally:
            await db.close()
    
    await audit.emit(session_id, "FIELDS_EXTRACTED", "STT", {
        "field_count": len(result.get("fields", {})),
        "model": result.get("model"),
    })
    
    return {"session_id": session_id, **result}


@router.post("/{session_id}/add-text")
async def add_text_transcript(session_id: str, text: str):
    """Manually add text to transcript (fallback for STT failure)."""
    session = store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    segments = session.get("transcript", [])
    segment = {
        "index": len(segments),
        "text": text,
        "confidence": 1.0,
        "timestamp": datetime.utcnow().isoformat(),
        "source": "manual",
    }
    store.append_transcript(session_id, segment)
    
    db = await get_db()
    try:
        await db.execute(
            """INSERT INTO transcripts (session_id, segment_index, text, confidence)
               VALUES (?, ?, ?, 1.0)""",
            (session_id, len(segments), text),
        )
        await db.commit()
    finally:
        await db.close()
    
    return {"status": "ok", "segment": segment}
