"""
M05 — LLM Intelligence Layer (Intent Classification & Risk Persona)
Uses Groq LLM with structured chain-of-thought reasoning.
"""

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
from models.llm_responses import AssessmentResponse

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

        try:
            validated = AssessmentResponse.from_raw(raw)
            result = validated.model_dump()
            result["model"] = settings.GROQ_MODEL
            return result
        except Exception as parse_err:
            print(f"[WARN] M05 Pydantic validation failed: {parse_err}")
            return {"error": "json parse failed", "model": settings.GROQ_MODEL}
        
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


# ──────────────────────────────────────────────────────────────────
# Free-Form Conversational Chat
# ──────────────────────────────────────────────────────────────────

CHAT_SYSTEM_PROMPT = """You are a friendly, professional AI loan advisor conducting a voice-based video call with a loan applicant.

Current session context:
- Interview stage: {stage}
- Collected fields so far: {fields_summary}
- Consent status: {consent_status}
- Offer status: {offer_status}

Rules:
1. Answer the user's question naturally and helpfully, like a real loan officer would.
2. You can answer about loans, EMIs, interest rates, banking concepts, eligibility, or even general questions.
3. Keep responses conversational and concise (2-4 sentences max) since this is a voice call.
4. If the user's message contains personal information (name, age, income, etc.), extract it naturally.
5. After answering, gently guide back to the interview if there are uncollected fields.
6. If the user says something like "I accept", "sounds good", "I agree", "yes I consent" — recognize it as acceptance/consent.
7. Be warm and empathetic but professional.

Respond with JSON:
{{
  "response": "Your conversational response (2-4 sentences, natural spoken language)",
  "extracted_data": {{
    "name": null,
    "age": null,
    "employment_type": null,
    "monthly_income": null,
    "loan_purpose": null,
    "requested_amount": null,
    "city": null
  }},
  "intent": "general_chat|answer_question|provide_info|accept_offer|give_consent|negotiate|decline",
  "should_advance_interview": false
}}

Only fill extracted_data fields if the user explicitly mentions them. Leave as null otherwise.
Set should_advance_interview to true if the user provided data for the currently expected field."""


class ChatRequest(BaseModel):
    message: str
    current_stage: Optional[str] = None


@router.post("/{session_id}/chat")
async def chat(session_id: str, req: ChatRequest):
    """
    Free-form conversational endpoint. The AI answers ANY question the user has,
    while staying in character as a loan advisor. Works at any pipeline stage.
    Also extracts data if the user mentions relevant info in passing.
    """
    session = store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    fields = session.get("extracted_fields", {})
    consent = session.get("consent")
    offer = session.get("offer")
    stage = req.current_stage or session.get("pipeline_stage", "INTERVIEW_GREETING")

    # Build fields summary
    fields_summary = []
    for k, v in fields.items():
        if isinstance(v, dict) and v.get("value"):
            fields_summary.append(f"{k}: {v['value']} ({v.get('confidence', 0):.0%} confidence)")
    fields_str = ", ".join(fields_summary) if fields_summary else "None collected yet"

    consent_status = "Obtained" if (consent and isinstance(consent, dict) and consent.get("is_consent")) else "Not yet"
    
    offer_status = "No offer generated"
    if offer:
        status = offer.get("status", "generated")
        if status == "accepted":
            offer_status = "Offer accepted"
        elif status == "declined":
            offer_status = "Offer declined"
        else:
            offer_status = f"Offer: ₹{offer.get('eligible_amount', 0):,.0f} at {offer.get('interest_rate', 0)}%"

    if not settings.has_groq_key:
        # Mock response
        response_text = f"That's a great question! Let me help you with that. As your AI loan advisor, I'm here to assist you with anything related to your loan application."
        
        # Check for acceptance/consent patterns
        msg_lower = req.message.lower()
        intent = "general_chat"
        if any(p in msg_lower for p in ["i accept", "sounds good", "that works", "i'll take it", "deal"]):
            intent = "accept_offer"
            response_text = "Wonderful! I'll process your acceptance right away."
        elif any(p in msg_lower for p in ["i agree", "i consent", "yes i consent", "go ahead"]):
            intent = "give_consent"
            response_text = "Thank you for your consent. I've recorded that. Let me proceed with your application."
        elif any(p in msg_lower for p in ["lower", "reduce", "discount", "less", "negotiate", "cheaper"]):
            intent = "negotiate"
            response_text = "I understand you'd like better terms. Let me see what I can adjust for you."
        
        return {
            "session_id": session_id,
            "response": response_text,
            "intent": intent,
            "extracted_data": {},
            "should_advance_interview": False,
            "model": "mock",
        }

    try:
        from groq import Groq
        client = Groq(api_key=settings.GROQ_API_KEY)

        system = CHAT_SYSTEM_PROMPT.format(
            stage=stage,
            fields_summary=fields_str,
            consent_status=consent_status,
            offer_status=offer_status,
        )

        response = client.chat.completions.create(
            model=settings.GROQ_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": req.message},
            ],
            temperature=0.6,
            max_tokens=512,
        )

        raw = response.choices[0].message.content.strip()
        # Strip markdown code fences
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        
        result = None
        
        # Strategy 1: Direct JSON parse
        try:
            result = json.loads(raw)
        except json.JSONDecodeError:
            pass
        
        # Strategy 2: Find JSON object in the text (LLM sometimes wraps it in text)
        if not result:
            import re
            json_match = re.search(r'\{[^{}]*"response"[^{}]*\}', raw, re.DOTALL)
            if json_match:
                try:
                    result = json.loads(json_match.group())
                except json.JSONDecodeError:
                    pass
        
        # Strategy 3: Find nested JSON (with nested objects like extracted_data)
        if not result:
            brace_start = raw.find('{')
            if brace_start >= 0:
                # Find matching closing brace
                depth = 0
                for i in range(brace_start, len(raw)):
                    if raw[i] == '{': depth += 1
                    elif raw[i] == '}': depth -= 1
                    if depth == 0:
                        try:
                            result = json.loads(raw[brace_start:i+1])
                        except json.JSONDecodeError:
                            pass
                        break

        # Strategy 4: Plain text fallback — clean it up
        if not result:
            # Remove any partial JSON that leaked
            clean = re.sub(r'\{[^}]*"response".*', '', raw).strip() if 'import re' or True else raw
            clean = re.sub(r'\{.*\}', '', raw, flags=re.DOTALL).strip()
            if not clean:
                clean = raw.split('{')[0].strip()  # Take text before first JSON
            if not clean:
                clean = "I understand. Let me help you with that."
            result = {
                "response": clean,
                "extracted_data": {},
                "intent": "general_chat",
                "should_advance_interview": False,
            }

        # Update extracted fields if LLM found new data
        extracted = result.get("extracted_data", {})
        if extracted and any(v is not None for v in extracted.values()):
            for field_name, value in extracted.items():
                if value is not None:
                    fields[field_name] = {"value": str(value), "confidence": 0.75}
            store.update(session_id, {"extracted_fields": fields})

        await audit.emit(session_id, "CHAT_MESSAGE", stage, {
            "user_message": req.message[:200],
            "intent": result.get("intent", "general_chat"),
            "extracted_fields": [k for k, v in extracted.items() if v is not None] if extracted else [],
        })

        return {
            "session_id": session_id,
            "response": result.get("response", "I understand. How can I help you further?"),
            "intent": result.get("intent", "general_chat"),
            "extracted_data": extracted,
            "should_advance_interview": result.get("should_advance_interview", False),
            "model": settings.GROQ_MODEL,
        }

    except Exception as e:
        print(f"[WARN] Chat failed: {e}")
        return {
            "session_id": session_id,
            "response": "I understand your question. Let me help you with that. Could you tell me more?",
            "intent": "general_chat",
            "extracted_data": {},
            "should_advance_interview": False,
            "error": str(e),
        }
