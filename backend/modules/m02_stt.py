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
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from typing import Optional

from config import settings
from database import get_db
from session_store import store
from events import audit
from modules.m_guardrails import check_relevance
from models.llm_responses import ExtractionResponse

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
    
    import re
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            from groq import Groq
            client = Groq(api_key=settings.GROQ_API_KEY)
            
            prompt = f"""You are a data extraction agent for a loan application. 
Extract the following fields from this conversation transcript. 
For each field, provide the extracted value and a confidence score (0.0 to 1.0).

Confidence scoring rules:
- 0.9-1.0: The value was explicitly and clearly stated by the applicant
- 0.7-0.89: The value was mentioned but somewhat ambiguous (e.g. "around 50K")
- 0.5-0.69: The value was inferred from context, not directly stated
- 0.0-0.49: The value is a guess or not mentioned at all
- If a field is not mentioned at all, set value to null and confidence to 0.0

Fields to extract:
- name: Full name of the applicant
- age: Age of the applicant (number)
- employment_type: Type of employment (salaried/self-employed/business/unemployed)
- monthly_income: Monthly income in INR (number only, no commas or currency symbols)
- loan_purpose: Purpose of the loan
- requested_amount: Requested loan amount in INR (number only, no commas or currency symbols)
- city: City of residence
- employer_name: Name of employer (if salaried)

Transcript:
\"\"\"{transcript}\"\"\"

Respond ONLY with valid JSON in this exact format, with NO trailing commas and NO markdown wrappers:
{{
  "name": {{"value": "extracted name or null", "confidence": 0.0}},
  "age": {{"value": "extracted age or null", "confidence": 0.0}},
  "employment_type": {{"value": "extracted type or null", "confidence": 0.0}},
  "monthly_income": {{"value": "extracted income or null", "confidence": 0.0}},
  "loan_purpose": {{"value": "extracted purpose or null", "confidence": 0.0}},
  "requested_amount": {{"value": "extracted amount or null", "confidence": 0.0}},
  "city": {{"value": "extracted city or null", "confidence": 0.0}},
  "employer_name": {{"value": "extracted employer or null", "confidence": 0.0}}
}}"""

            response = client.chat.completions.create(
                model=settings.GROQ_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1 + (0.2 * attempt), # Increase temperature slightly on retries
                max_tokens=512,
            )
            
            raw = response.choices[0].message.content.strip()

            try:
                validated = ExtractionResponse.from_raw(raw)
                fields = validated.model_dump()
                return {"fields": fields, "model": settings.GROQ_MODEL}
            except Exception as parse_err:
                print(f"[WARN] Pydantic validation failed on attempt {attempt + 1}: {parse_err}")
                
        except Exception as e:
            print(f"[WARN] LLM extraction failed on attempt {attempt + 1}: {e}")
            
    # If all retries fail
    print("[ERROR] Max retries exhausted for LLM extraction.")
    return {"fields": {}, "model": "error", "error": "json parse failed after retries"}


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
                    word_timestamps: list[dict] = []
                else:
                    # Real transcription with faster-whisper
                    word_timestamps = []
                    try:
                        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                            tmp.write(audio_bytes)
                            tmp_path = tmp.name

                        segments_iter, info = model.transcribe(
                            tmp_path,
                            beam_size=1,
                            language="en",
                            vad_filter=True,
                            word_timestamps=True,
                        )

                        parts = []
                        for seg in segments_iter:
                            parts.append(seg.text)
                            confidence = max(confidence, seg.avg_logprob)
                            # Collect per-word timestamps for video clip extraction
                            if hasattr(seg, "words") and seg.words:
                                for w in seg.words:
                                    word_timestamps.append({
                                        "word": w.word.strip(),
                                        "start": round(w.start, 3),
                                        "end": round(w.end, 3),
                                    })

                        text = " ".join(parts).strip()
                        os.unlink(tmp_path)

                        # Convert log prob to 0-1 confidence
                        import math
                        confidence = math.exp(confidence) if confidence < 0 else confidence

                    except Exception as e:
                        text = ""
                        word_timestamps = []
                        print(f"[WARN] Whisper error: {e}")

                if text:
                    # ── Guardrail check ──────────────────────────────────
                    session = store.get(session_id)
                    pipeline_stage = session.get("pipeline_stage", "") if session else ""
                    # Only enforce guardrails during the interview flow
                    interview_stages = {
                        "INTERVIEW_GREETING", "AWAIT_NAME", "AWAIT_AGE",
                        "AWAIT_EMPLOYMENT", "AWAIT_INCOME", "AWAIT_LOAN_PURPOSE",
                        "AWAIT_AMOUNT", "AWAIT_CONSENT",
                    }
                    redirect_msg: str | None = None
                    if pipeline_stage in interview_stages:
                        # Determine next missing field for the redirect prompt
                        fields = session.get("extracted_fields", {}) if session else {}
                        field_order = ["name", "age", "employment_type", "monthly_income",
                                       "loan_purpose", "requested_amount"]
                        next_field = next(
                            (f for f in field_order
                             if not (fields.get(f) or {}).get("value")),
                            None,
                        )
                        guard = check_relevance(text, next_field)
                        if not guard["is_relevant"]:
                            redirect_msg = guard["redirect_msg"]

                    segment = {
                        "index": segment_index,
                        "text": text,
                        "confidence": round(confidence, 3),
                        "timestamp": datetime.utcnow().isoformat(),
                        "word_timestamps": word_timestamps,
                    }

                    # Store in memory (word_timestamps stored for video clip extraction)
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

                    # Send back to client — include redirect if off-topic
                    response_payload: dict = {
                        "type": "transcript",
                        "segment": segment,
                    }
                    if redirect_msg:
                        response_payload["guardrail"] = {
                            "off_topic": True,
                            "redirect_message": redirect_msg,
                            "similarity": guard.get("similarity", 0),
                        }

                    await websocket.send_json(response_payload)
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
    
    # Clean transcript for better LLM extraction:
    # Convert "[AI Question: X] answer" into "AI: X\nApplicant: answer" format
    import re
    clean = transcript
    # Replace [AI Question: ...] markers with clear labels
    clean = re.sub(r'\[AI Question:\s*', '\nAI: ', clean)
    clean = clean.replace(']', '\nApplicant: ')
    # Remove consecutive "Applicant:" labels without content
    clean = re.sub(r'Applicant:\s*\n', '\n', clean)
    # Clean up extra whitespace
    clean = re.sub(r'\n{2,}', '\n', clean).strip()
    
    result = await _extract_fields_llm(clean, session_id)
    
    # Store extracted fields — MERGE with existing, keep higher confidence
    if result.get("fields"):
        session = store.get(session_id)
        existing = session.get("extracted_fields", {}) if session else {}
        merged = dict(existing)  # start from existing

        for field_name, new_data in result["fields"].items():
            old_data = existing.get(field_name, {})
            # Normalise both to dicts
            if not isinstance(new_data, dict):
                new_data = {"value": new_data, "confidence": 1.0 if new_data else 0}
            if not isinstance(old_data, dict):
                old_data = {"value": old_data, "confidence": 1.0 if old_data else 0}

            new_val = new_data.get("value")
            new_conf = new_data.get("confidence", 0)
            old_val = old_data.get("value")
            old_conf = old_data.get("confidence", 0)

            # Keep new value only if it actually has content AND beats old confidence,
            # or if old value was empty
            if new_val and (not old_val or new_conf >= old_conf):
                merged[field_name] = new_data
            elif old_val:
                merged[field_name] = old_data
            else:
                merged[field_name] = new_data  # both empty, take new

        result["fields"] = merged
        store.update(session_id, {"extracted_fields": merged})
        
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


@router.get("/{session_id}/export")
async def export_transcript(session_id: str):
    """
    Export the full session transcript as a plain-text file.
    Format: Segment N [HH:MM:SS]: 'text...'
    Returns text/plain with a Content-Disposition download header.
    """
    # Try memory first
    session = store.get(session_id)
    segments = []
    if session and session.get("transcript"):
        segments = session["transcript"]
    else:
        db = await get_db()
        try:
            cursor = await db.execute(
                "SELECT segment_index, text, confidence, created_at FROM transcripts "
                "WHERE session_id = ? ORDER BY segment_index",
                (session_id,),
            )
            rows = await cursor.fetchall()
            segments = [dict(r) for r in rows]
        finally:
            await db.close()

    if not segments:
        raise HTTPException(status_code=404, detail="No transcript found for this session")

    lines: list[str] = [
        f"AgentFinance AI — Session Transcript",
        f"Session ID : {session_id}",
        f"Exported   : {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC",
        "=" * 60,
        "",
    ]
    for seg in segments:
        # Normalise timestamp to HH:MM:SS
        ts_raw = seg.get("timestamp") or seg.get("created_at") or ""
        try:
            dt = datetime.fromisoformat(ts_raw.rstrip("Z"))
            ts_fmt = dt.strftime("%H:%M:%S")
        except Exception:
            ts_fmt = "00:00:00"
        idx = seg.get("index", seg.get("segment_index", "?"))
        conf = seg.get("confidence", 0)
        lines.append(f"Segment {idx} [{ts_fmt}] (conf {conf:.2f}): {seg['text']}")

    content = "\n".join(lines)
    filename = f"transcript-{session_id[:8]}.txt"
    return PlainTextResponse(
        content=content,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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
