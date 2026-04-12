"""
M09 — Agentic Orchestration, Recovery & Fallback Handling
Stateful session manager with FSM, failure modes, recovery paths,
and structured AI interview sub-states.
"""

import json
from datetime import datetime
from enum import Enum
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from config import settings
from database import get_db
from session_store import store
from events import audit

router = APIRouter(prefix="/api/orchestrator", tags=["M09 - Orchestrator"])


# ──────────────────────────────────────────────────────────────────
# Pipeline Stages (FSM States) — includes interview sub-states
# ──────────────────────────────────────────────────────────────────

class PipelineStage(str, Enum):
    SESSION_INIT = "SESSION_INIT"
    METADATA_CAPTURE = "METADATA_CAPTURE"
    # --- Interview sub-states ---
    INTERVIEW_GREETING = "INTERVIEW_GREETING"
    AWAIT_NAME = "AWAIT_NAME"
    AWAIT_AGE = "AWAIT_AGE"
    AWAIT_EMPLOYMENT = "AWAIT_EMPLOYMENT"
    AWAIT_INCOME = "AWAIT_INCOME"
    AWAIT_LOAN_PURPOSE = "AWAIT_LOAN_PURPOSE"
    AWAIT_AMOUNT = "AWAIT_AMOUNT"
    AWAIT_CONSENT = "AWAIT_CONSENT"
    # --- Post-interview pipeline ---
    STT_ACTIVE = "STT_ACTIVE"
    FIELD_EXTRACTION = "FIELD_EXTRACTION"
    CONSENT_CHECK = "CONSENT_CHECK"
    LIVENESS_CHECK = "LIVENESS_CHECK"
    LLM_ANALYSIS = "LLM_ANALYSIS"
    FRAUD_SCORING = "FRAUD_SCORING"
    BUREAU_CHECK = "BUREAU_CHECK"
    OFFER_GENERATION = "OFFER_GENERATION"
    NEGOTIATION = "NEGOTIATION"
    SESSION_COMPLETE = "SESSION_COMPLETE"
    SESSION_FAILED = "SESSION_FAILED"


# ──────────────────────────────────────────────────────────────────
# Interview Question Templates
# ──────────────────────────────────────────────────────────────────

INTERVIEW_QUESTIONS = {
    "INTERVIEW_GREETING": "Hello! I'm your AI loan advisor. I'll guide you through a quick application process. Let's start — what is your full name?",
    "AWAIT_NAME": "Could you please tell me your full name?",
    "AWAIT_AGE": "Thank you, {name}! How old are you?",
    "AWAIT_EMPLOYMENT": "Great. And what type of employment do you have? Are you salaried, self-employed, or running a business?",
    "AWAIT_INCOME": "What is your approximate monthly income in rupees?",
    "AWAIT_LOAN_PURPOSE": "What would you like the loan for? For example, home improvement, education, medical expenses, or something else?",
    "AWAIT_AMOUNT": "And how much loan amount are you looking for?",
    "AWAIT_CONSENT": "Excellent! I have all the information I need. Before I process your application, I need your verbal consent. Could you please say 'I agree' or 'Yes, I consent' to proceed with the loan application?",
}

# Maps interview stages to the field they're collecting
INTERVIEW_STAGE_FIELD_MAP = {
    "AWAIT_NAME": "name",
    "AWAIT_AGE": "age",
    "AWAIT_EMPLOYMENT": "employment_type",
    "AWAIT_INCOME": "monthly_income",
    "AWAIT_LOAN_PURPOSE": "loan_purpose",
    "AWAIT_AMOUNT": "requested_amount",
}

# Ordered interview flow
INTERVIEW_FLOW = [
    "INTERVIEW_GREETING",
    "AWAIT_NAME",
    "AWAIT_AGE",
    "AWAIT_EMPLOYMENT",
    "AWAIT_INCOME",
    "AWAIT_LOAN_PURPOSE",
    "AWAIT_AMOUNT",
    "AWAIT_CONSENT",
]


# Valid transitions (updated with interview sub-states)
VALID_TRANSITIONS = {
    PipelineStage.SESSION_INIT: [PipelineStage.METADATA_CAPTURE],
    PipelineStage.METADATA_CAPTURE: [PipelineStage.INTERVIEW_GREETING, PipelineStage.STT_ACTIVE, PipelineStage.SESSION_FAILED],
    PipelineStage.INTERVIEW_GREETING: [PipelineStage.AWAIT_NAME],
    PipelineStage.AWAIT_NAME: [PipelineStage.AWAIT_AGE, PipelineStage.AWAIT_NAME],
    PipelineStage.AWAIT_AGE: [PipelineStage.AWAIT_EMPLOYMENT, PipelineStage.AWAIT_AGE],
    PipelineStage.AWAIT_EMPLOYMENT: [PipelineStage.AWAIT_INCOME, PipelineStage.AWAIT_EMPLOYMENT],
    PipelineStage.AWAIT_INCOME: [PipelineStage.AWAIT_LOAN_PURPOSE, PipelineStage.AWAIT_INCOME],
    PipelineStage.AWAIT_LOAN_PURPOSE: [PipelineStage.AWAIT_AMOUNT, PipelineStage.AWAIT_LOAN_PURPOSE],
    PipelineStage.AWAIT_AMOUNT: [PipelineStage.AWAIT_CONSENT, PipelineStage.AWAIT_AMOUNT],
    PipelineStage.AWAIT_CONSENT: [PipelineStage.LIVENESS_CHECK, PipelineStage.AWAIT_CONSENT, PipelineStage.SESSION_FAILED],
    PipelineStage.STT_ACTIVE: [PipelineStage.FIELD_EXTRACTION, PipelineStage.SESSION_FAILED],
    PipelineStage.FIELD_EXTRACTION: [PipelineStage.CONSENT_CHECK, PipelineStage.STT_ACTIVE, PipelineStage.SESSION_FAILED],
    PipelineStage.CONSENT_CHECK: [PipelineStage.LIVENESS_CHECK, PipelineStage.SESSION_FAILED],
    PipelineStage.LIVENESS_CHECK: [PipelineStage.LLM_ANALYSIS, PipelineStage.LIVENESS_CHECK, PipelineStage.SESSION_FAILED],
    PipelineStage.LLM_ANALYSIS: [PipelineStage.FRAUD_SCORING, PipelineStage.SESSION_FAILED],
    PipelineStage.FRAUD_SCORING: [PipelineStage.BUREAU_CHECK, PipelineStage.SESSION_FAILED],
    PipelineStage.BUREAU_CHECK: [PipelineStage.OFFER_GENERATION, PipelineStage.SESSION_FAILED],
    PipelineStage.OFFER_GENERATION: [PipelineStage.NEGOTIATION, PipelineStage.SESSION_COMPLETE],
    PipelineStage.NEGOTIATION: [PipelineStage.SESSION_COMPLETE, PipelineStage.SESSION_FAILED],
}


# ──────────────────────────────────────────────────────────────────
# Failure Modes
# ──────────────────────────────────────────────────────────────────

FAILURE_MODES = {
    "FM-01": {
        "name": "STT_FAILURE",
        "description": "Speech-to-text engine failed or audio quality too low",
        "recovery_path": "Fallback to text input mode — prompt user to type responses",
        "escalation_rule": "If text input also fails after 3 retries, terminate session",
        "retry_limit": 3,
        "stage": PipelineStage.STT_ACTIVE,
    },
    "FM-02": {
        "name": "LIVENESS_FAILURE",
        "description": "Liveness detection could not confirm physical presence",
        "recovery_path": "Prompt user for better lighting/angle, retry up to 3 times",
        "escalation_rule": "After 3 failed attempts, reject session with anti-fraud flag",
        "retry_limit": 3,
        "stage": PipelineStage.LIVENESS_CHECK,
    },
    "FM-03": {
        "name": "BUREAU_TIMEOUT",
        "description": "Credit bureau service did not respond within timeout",
        "recovery_path": "Use cached/default credit score, mark decision as REFER",
        "escalation_rule": "If bureau unreachable for 5+ minutes, complete with REFER status",
        "retry_limit": 2,
        "stage": PipelineStage.BUREAU_CHECK,
    },
    "FM-04": {
        "name": "VIDEO_DISCONNECT",
        "description": "Video/audio connection dropped mid-session",
        "recovery_path": "Generate resume link, preserve FSM state, allow re-entry within 10 mins",
        "escalation_rule": "If no reconnection within 10 minutes, archive session as incomplete",
        "retry_limit": 1,
        "stage": PipelineStage.STT_ACTIVE,
    },
    "FM-05": {
        "name": "FRAUD_ESCALATION",
        "description": "Fraud score exceeds critical threshold (80+)",
        "recovery_path": "Auto-terminate session immediately, generate fraud alert",
        "escalation_rule": "Log full session data, flag for compliance review",
        "retry_limit": 0,
        "stage": PipelineStage.FRAUD_SCORING,
    },
    "FM-06": {
        "name": "LLM_FAILURE",
        "description": "LLM API call failed or returned invalid response",
        "recovery_path": "Retry with simplified prompt, fall back to rule-based classification",
        "escalation_rule": "After 2 retries, use default moderate_borrower persona",
        "retry_limit": 2,
        "stage": PipelineStage.LLM_ANALYSIS,
    },
}


# ──────────────────────────────────────────────────────────────────
# Orchestrator Logic
# ──────────────────────────────────────────────────────────────────

async def _transition(session_id: str, to_stage: PipelineStage, success: bool = True, error: str = None) -> dict:
    """Execute a state transition with audit logging."""
    session = store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    current = session.get("pipeline_stage", PipelineStage.SESSION_INIT.value)
    
    # Record transition
    event_data = {
        "from_stage": current,
        "to_stage": to_stage.value,
        "success": success,
        "error": error,
    }
    
    updates = {
        "pipeline_stage": to_stage.value,
    }
    
    completed = session.get("stages_completed", [])
    failed = session.get("stages_failed", [])
    
    if success and current not in completed:
        completed.append(current)
        updates["stages_completed"] = completed
    elif not success:
        if current not in failed:
            failed.append(current)
        updates["stages_failed"] = failed
    
    store.update(session_id, updates)
    
    # Persist state
    try:
        db = await get_db()
        try:
            await db.execute(
                """INSERT OR REPLACE INTO pipeline_states
                   (session_id, current_stage, stages_completed, stages_failed, updated_at)
                   VALUES (?, ?, ?, ?, datetime('now'))""",
                (session_id, to_stage.value, json.dumps(completed), json.dumps(failed)),
            )
            await db.commit()
        finally:
            await db.close()
    except Exception:
        pass
    
    await audit.emit(session_id, "STAGE_TRANSITION", to_stage.value, event_data)
    
    return {
        "session_id": session_id,
        "previous_stage": current,
        "current_stage": to_stage.value,
        "success": success,
        "stages_completed": completed,
        "stages_failed": failed,
    }


class TransitionRequest(BaseModel):
    to_stage: str
    success: bool = True
    error: Optional[str] = None

class FailureReport(BaseModel):
    failure_mode: str  # e.g. "FM-01"
    details: Optional[str] = None


# ──────────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────────

@router.post("/{session_id}/transition")
async def transition_stage(session_id: str, req: TransitionRequest):
    """Manually trigger a state transition."""
    try:
        stage = PipelineStage(req.to_stage)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid stage: {req.to_stage}")
    
    return await _transition(session_id, stage, req.success, req.error)


@router.post("/{session_id}/advance")
async def advance_pipeline(session_id: str):
    """
    Auto-advance to the next logical pipeline stage.
    Runs the current stage's processing and transitions accordingly.
    """
    session = store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    current = session.get("pipeline_stage", PipelineStage.SESSION_INIT.value)
    
    # Determine next stage
    stage_order = [s.value for s in PipelineStage if s not in (PipelineStage.SESSION_FAILED,)]
    current_idx = stage_order.index(current) if current in stage_order else 0
    
    if current_idx + 1 >= len(stage_order):
        return {"session_id": session_id, "message": "Pipeline already complete", "stage": current}
    
    next_stage = PipelineStage(stage_order[current_idx + 1])
    return await _transition(session_id, next_stage)


@router.post("/{session_id}/failure")
async def report_failure(session_id: str, req: FailureReport):
    """
    Report a failure mode and get recovery instructions.
    """
    mode = FAILURE_MODES.get(req.failure_mode)
    if not mode:
        raise HTTPException(status_code=400, detail=f"Unknown failure mode: {req.failure_mode}")
    
    session = store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    store.update(session_id, {
        "failure_mode": req.failure_mode,
    })
    
    # Persist
    try:
        db = await get_db()
        try:
            await db.execute(
                """UPDATE pipeline_states SET failure_mode = ?, recovery_action = ?, updated_at = datetime('now')
                   WHERE session_id = ?""",
                (req.failure_mode, mode["recovery_path"], session_id),
            )
            await db.commit()
        finally:
            await db.close()
    except Exception:
        pass
    
    await audit.emit(session_id, "FAILURE_REPORTED", mode["stage"].value, {
        "failure_mode": req.failure_mode,
        "name": mode["name"],
        "details": req.details,
        "recovery_path": mode["recovery_path"],
    })
    
    # Auto-terminate on fraud escalation
    if req.failure_mode == "FM-05":
        await _transition(session_id, PipelineStage.SESSION_FAILED, success=False, error="Fraud escalation")
    
    return {
        "session_id": session_id,
        "failure_mode": mode,
        "recovery_instructions": mode["recovery_path"],
        "escalation_rule": mode["escalation_rule"],
        "retry_limit": mode["retry_limit"],
    }


@router.get("/{session_id}/state")
async def get_pipeline_state(session_id: str):
    """Get current pipeline state."""
    session = store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return {
        "session_id": session_id,
        "current_stage": session.get("pipeline_stage", "SESSION_INIT"),
        "stages_completed": session.get("stages_completed", []),
        "stages_failed": session.get("stages_failed", []),
        "failure_mode": session.get("failure_mode"),
        "status": session.get("status", "unknown"),
    }


@router.get("/{session_id}/timeline")
async def get_timeline(session_id: str):
    """Get full stage timeline from audit events."""
    events = audit.get_events(session_id)
    
    if not events:
        events = await audit.get_events_from_db(session_id)
    
    # Filter to stage transitions
    transitions = [e for e in events if e["event_type"] == "STAGE_TRANSITION"]
    
    return {
        "session_id": session_id,
        "transitions": transitions,
        "total_events": len(events),
        "all_events": events,
    }


@router.get("/failure-modes")
async def list_failure_modes():
    """List all defined failure modes with recovery paths."""
    return {
        "failure_modes": {
            k: {**v, "stage": v["stage"].value}
            for k, v in FAILURE_MODES.items()
        }
    }


# ──────────────────────────────────────────────────────────────────
# Interview Flow Endpoints
# ──────────────────────────────────────────────────────────────────

@router.post("/{session_id}/interview-next")
async def interview_next(session_id: str):
    """
    Determine the next interview question based on which fields are still missing.
    Advances the FSM to the appropriate interview sub-state.
    Returns the next question for the AI to speak.
    """
    session = store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    current = session.get("pipeline_stage", PipelineStage.SESSION_INIT.value)
    fields = session.get("extracted_fields", {})
    consent = session.get("consent")

    # Check if consent was obtained — if so, interview is done
    if consent and isinstance(consent, dict) and consent.get("is_consent"):
        return {
            "session_id": session_id,
            "interview_complete": True,
            "current_stage": current,
            "message": "Interview complete. Consent obtained. Ready for pipeline processing.",
            "next_action": "run_pipeline",
        }

    # Find the next missing field
    next_stage = None
    for stage_name in INTERVIEW_FLOW:
        if stage_name == "INTERVIEW_GREETING":
            # Skip greeting if we're past it
            if current != PipelineStage.SESSION_INIT.value and current != PipelineStage.METADATA_CAPTURE.value and current != "INTERVIEW_GREETING":
                continue
            if current in (PipelineStage.SESSION_INIT.value, PipelineStage.METADATA_CAPTURE.value):
                next_stage = stage_name
                break
            continue

        if stage_name == "AWAIT_CONSENT":
            # Only ask for consent if all data fields are collected
            all_collected = True
            for field_stage, field_name in INTERVIEW_STAGE_FIELD_MAP.items():
                field_data = fields.get(field_name, {})
                if isinstance(field_data, dict):
                    val = field_data.get("value")
                    conf = field_data.get("confidence", 0)
                else:
                    val = field_data
                    conf = 1.0 if field_data else 0
                if not val or conf < 0.3:
                    all_collected = False
                    break
            if all_collected:
                next_stage = "AWAIT_CONSENT"
                break
            continue

        # Check if this field is missing or low confidence
        field_name = INTERVIEW_STAGE_FIELD_MAP.get(stage_name)
        if field_name:
            field_data = fields.get(field_name, {})
            if isinstance(field_data, dict):
                val = field_data.get("value")
                conf = field_data.get("confidence", 0)
            else:
                val = field_data
                conf = 1.0 if field_data else 0

            if not val or conf < 0.3:
                next_stage = stage_name
                break

    if not next_stage:
        # All fields collected, ask for consent
        next_stage = "AWAIT_CONSENT"

    # Format the question with dynamic field values
    question_template = INTERVIEW_QUESTIONS.get(next_stage, "Could you tell me more?")
    try:
        name_val = ""
        if isinstance(fields.get("name"), dict):
            name_val = fields["name"].get("value", "")
        elif isinstance(fields.get("name"), str):
            name_val = fields["name"]
        question = question_template.format(
            name=name_val or "there",
        )
    except (KeyError, IndexError):
        question = question_template

    # Transition FSM
    try:
        stage_enum = PipelineStage(next_stage)
        await _transition(session_id, stage_enum)
    except (ValueError, Exception):
        pass

    # Calculate interview progress
    current_step = INTERVIEW_FLOW.index(next_stage) + 1 if next_stage in INTERVIEW_FLOW else 0
    total_steps = len(INTERVIEW_FLOW)

    # Summarise collected fields
    collected = {}
    for field_name, field_data in fields.items():
        if isinstance(field_data, dict) and field_data.get("value"):
            collected[field_name] = {
                "value": field_data["value"],
                "confidence": field_data.get("confidence", 0),
            }

    await audit.emit(session_id, "INTERVIEW_QUESTION", next_stage, {
        "question": question[:100],
        "step": current_step,
        "total_steps": total_steps,
    })

    return {
        "session_id": session_id,
        "interview_complete": False,
        "current_stage": next_stage,
        "question": question,
        "step": current_step,
        "total_steps": total_steps,
        "expected_field": INTERVIEW_STAGE_FIELD_MAP.get(next_stage),
        "collected_fields": collected,
    }


@router.get("/{session_id}/interview-status")
async def interview_status(session_id: str):
    """Get current interview progress — which fields are collected and their confidence."""
    session = store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    fields = session.get("extracted_fields", {})
    consent = session.get("consent")

    status_map = {}
    for stage_name, field_name in INTERVIEW_STAGE_FIELD_MAP.items():
        field_data = fields.get(field_name, {})
        if isinstance(field_data, dict):
            status_map[field_name] = {
                "value": field_data.get("value"),
                "confidence": field_data.get("confidence", 0),
                "collected": bool(field_data.get("value")),
                "stage": stage_name,
            }
        else:
            status_map[field_name] = {
                "value": field_data,
                "confidence": 1.0 if field_data else 0,
                "collected": bool(field_data),
                "stage": stage_name,
            }

    collected_count = sum(1 for v in status_map.values() if v["collected"])
    total_fields = len(status_map)
    avg_confidence = (
        sum(v["confidence"] for v in status_map.values() if v["collected"]) / collected_count
        if collected_count > 0 else 0
    )

    return {
        "session_id": session_id,
        "fields": status_map,
        "collected_count": collected_count,
        "total_fields": total_fields,
        "avg_confidence": round(avg_confidence, 3),
        "consent_obtained": bool(consent and isinstance(consent, dict) and consent.get("is_consent")),
        "interview_complete": collected_count >= total_fields and bool(consent and isinstance(consent, dict) and consent.get("is_consent")),
    }
