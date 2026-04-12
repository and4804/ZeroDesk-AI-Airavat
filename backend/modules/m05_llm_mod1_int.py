"""
M05 — LLM Intelligence Layer (Intent Classification & Risk Persona)
Uses Groq LLM with structured chain-of-thought reasoning.
"""

import json
from datetime import datetime
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from config import settings
from database import get_db
from session_store import store
from events import audit

router = APIRouter(prefix="/api/llm", tags=["M05 - LLM"])


ANALYSIS_PROMPT = """You are a loan application analyst AI. Analyze the following loan application transcript and provide a structured assessment.

## Applicant Information (extracted):
{fields_json}

## Full Transcript:
\"\"\"{transcript}\"\"\"

## Your Task:
1. **Intent Classification**: Categorize the loan purpose into ONE of these categories:
   - home_improvement, medical_emergency, education, debt_consolidation, vehicle_purchase, 
   - business_expansion, wedding, travel, consumer_electronics, other
   Provide a confidence score (0.0-1.0).

2. **Risk Persona**: Assign ONE risk persona:
   - conservative_borrower: Careful, plans well, stable income, low-risk purpose
   - moderate_borrower: Standard profile, employed, reasonable request
   - aggressive_borrower: Requesting high amounts relative to income, multiple purposes
   - first_time_borrower: No credit history mentioned, uncertain language
   - distressed_borrower: Urgency in language, mentions of financial difficulty
   Provide a confidence score (0.0-1.0).

3. **Contradiction Detection**: Identify any contradictions in the transcript (e.g., income vs lifestyle, stated employment vs other clues).

4. **Chain-of-Thought Reasoning**: Explain your reasoning step by step. This is MANDATORY — no black-box outputs.

Respond ONLY with valid JSON:
{{
  "intent_category": "home_improvement",
  "intent_confidence": 0.85,
  "risk_persona": "moderate_borrower", 
  "risk_confidence": 0.78,
  "reasoning_trace": [
    "Step 1: The applicant mentioned...",
    "Step 2: Based on the income of...",
    "Step 3: The loan purpose aligns with...",
    "Step 4: Overall risk assessment..."
  ],
  "contradictions": [
    {{"field1": "income", "field2": "loan_amount", "description": "...", "severity": "low"}}
  ],
  "tone_indicators": ["calm", "confident"],
  "distress_signals": false,
  "summary": "Brief one-line summary of the assessment"
}}"""


CLARIFICATION_PROMPT = """You are a friendly loan officer AI conducting a video call with an applicant. 
The following fields need clarification because they have low confidence or are missing.

Missing/Low-confidence fields: {fields}

Generate a natural, conversational question to ask the applicant to clarify these fields.
Be polite, professional, and ask about ONE field at a time.
Keep it to 1-2 sentences maximum.

Respond with just the question text, nothing else."""


async def _run_llm_analysis(transcript: str, fields: dict) -> dict:
    """Run LLM analysis on transcript."""
    if not settings.has_groq_key:
        return {
            "intent_category": "home_improvement",
            "intent_confidence": 0.82,
            "risk_persona": "moderate_borrower",
            "risk_confidence": 0.75,
            "reasoning_trace": [
                "Step 1: Applicant data extracted from transcript.",
                "Step 2: Income level suggests moderate borrowing capacity.",
                "Step 3: Loan purpose appears to be home improvement based on stated intent.",
                "Step 4: No significant distress signals detected in language patterns.",
                "Step 5: Overall assessment: moderate risk, standard borrower profile.",
            ],
            "contradictions": [],
            "tone_indicators": ["calm", "cooperative"],
            "distress_signals": False,
            "summary": "Standard moderate-risk applicant seeking home improvement loan.",
            "model": "mock",
        }
    
    try:
        from groq import Groq
        client = Groq(api_key=settings.GROQ_API_KEY)
        
        prompt = ANALYSIS_PROMPT.format(
            fields_json=json.dumps(fields, indent=2),
            transcript=transcript[:3000],  # Truncate for token limits
        )
        
        response = client.chat.completions.create(
            model=settings.GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=1024,
        )
        
        raw = response.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
        
        result = json.loads(raw)
        result["model"] = settings.GROQ_MODEL
        return result
        
    except Exception as e:
        print(f"[WARN] LLM analysis failed: {e}")
        return {"error": str(e), "model": "error"}


async def _generate_clarification(fields: list[str]) -> str:
    """Generate a clarification question for missing fields."""
    if not settings.has_groq_key:
        return f"Could you please tell me more about your {fields[0]}?"
    
    try:
        from groq import Groq
        client = Groq(api_key=settings.GROQ_API_KEY)
        
        response = client.chat.completions.create(
            model=settings.GROQ_MODEL,
            messages=[{
                "role": "user",
                "content": CLARIFICATION_PROMPT.format(fields=", ".join(fields)),
            }],
            temperature=0.7,
            max_tokens=128,
        )
        
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"Could you please clarify your {fields[0]}?"


# ──────────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────────

@router.post("/{session_id}/analyze")
async def analyze_session(session_id: str):
    """Run LLM analysis: intent classification + risk persona + CoT reasoning."""
    session = store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    transcript = store.get_full_transcript(session_id)
    fields = session.get("extracted_fields", {})
    
    if not transcript and not fields:
        raise HTTPException(status_code=400, detail="No transcript or fields available for analysis")
    
    result = await _run_llm_analysis(transcript or "No transcript available", fields)
    
    # Store assessment
    store.update(session_id, {"llm_assessment": result})
    
    # Persist to DB
    try:
        db = await get_db()
        try:
            await db.execute(
                """INSERT INTO llm_assessments 
                   (session_id, intent_category, intent_confidence, risk_persona, 
                    risk_confidence, reasoning_trace, contradictions)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    session_id,
                    result.get("intent_category"),
                    result.get("intent_confidence"),
                    result.get("risk_persona"),
                    result.get("risk_confidence"),
                    json.dumps(result.get("reasoning_trace", [])),
                    json.dumps(result.get("contradictions", [])),
                ),
            )
            await db.commit()
        finally:
            await db.close()
    except Exception:
        pass
    
    await audit.emit(session_id, "LLM_ANALYSIS_COMPLETED", "LLM", {
        "intent": result.get("intent_category"),
        "risk_persona": result.get("risk_persona"),
        "distress_signals": result.get("distress_signals", False),
        "contradiction_count": len(result.get("contradictions", [])),
    })
    
    return {"session_id": session_id, "assessment": result}


@router.post("/{session_id}/clarify")
async def generate_clarification(session_id: str):
    """Generate a clarification question for low-confidence fields."""
    session = store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    fields = session.get("extracted_fields", {})
    low_confidence = [
        name for name, data in fields.items()
        if isinstance(data, dict) and data.get("confidence", 1.0) < 0.6
    ]
    missing = [
        name for name, data in fields.items()
        if isinstance(data, dict) and data.get("value") is None
    ]
    
    needs_clarification = low_confidence + missing
    if not needs_clarification:
        return {"session_id": session_id, "question": None, "message": "All fields have sufficient confidence"}
    
    question = await _generate_clarification(needs_clarification)
    
    await audit.emit(session_id, "CLARIFICATION_REQUESTED", "LLM", {
        "fields": needs_clarification,
        "question": question,
    })
    
    return {
        "session_id": session_id,
        "question": question,
        "fields_needing_clarification": needs_clarification,
    }


@router.get("/{session_id}/assessment")
async def get_assessment(session_id: str):
    """Get the LLM assessment for a session."""
    session = store.get(session_id)
    if session and session.get("llm_assessment"):
        return {"session_id": session_id, "assessment": session["llm_assessment"]}
    
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM llm_assessments WHERE session_id = ? ORDER BY created_at DESC LIMIT 1",
            (session_id,),
        )
        row = await cursor.fetchone()
        if row:
            data = dict(row)
            data["reasoning_trace"] = json.loads(data.get("reasoning_trace", "[]"))
            data["contradictions"] = json.loads(data.get("contradictions", "[]"))
            return {"session_id": session_id, "assessment": data}
    finally:
        await db.close()
    
    raise HTTPException(status_code=404, detail="No assessment found")
