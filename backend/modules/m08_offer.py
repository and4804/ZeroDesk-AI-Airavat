"""
M08 — Personalised Loan Offer Generation & Negotiation Agent
Generates offers based on fraud+policy+risk data, LLM-powered negotiation.
"""

import json
import uuid
import math
from datetime import datetime
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from config import settings
from database import get_db
from session_store import store
from events import audit

router = APIRouter(prefix="/api/offer", tags=["M08 - Offer"])


# ──────────────────────────────────────────────────────────────────
# Offer Calculation Engine
# ──────────────────────────────────────────────────────────────────

def _calculate_emi(principal: float, annual_rate: float, tenure_months: int) -> float:
    """Standard EMI calculation using reducing balance method."""
    if annual_rate == 0:
        return principal / tenure_months
    monthly_rate = annual_rate / 12 / 100
    emi = principal * monthly_rate * math.pow(1 + monthly_rate, tenure_months) / \
          (math.pow(1 + monthly_rate, tenure_months) - 1)
    return round(emi, 2)


def _generate_offer(session: dict) -> dict:
    """Generate personalised loan offer from all pipeline data."""
    fields = session.get("extracted_fields", {})
    fraud = session.get("fraud_score", {})
    bureau = session.get("bureau_result", {})
    llm = session.get("llm_assessment", {})
    
    # Extract values
    monthly_income = 0
    requested_amount = 0
    
    if isinstance(fields.get("monthly_income"), dict):
        try:
            monthly_income = float(fields["monthly_income"].get("value", 0))
        except (ValueError, TypeError):
            monthly_income = 50000  # Default
    
    if isinstance(fields.get("requested_amount"), dict):
        try:
            requested_amount = float(fields["requested_amount"].get("value", 0))
        except (ValueError, TypeError):
            requested_amount = 500000  # Default
    
    if monthly_income == 0:
        monthly_income = 50000
    if requested_amount == 0:
        requested_amount = 500000
    
    annual_income = monthly_income * 12
    
    # Credit score from bureau
    bureau_data = bureau.get("bureau_data", {}) if isinstance(bureau, dict) else {}
    credit_score = bureau_data.get("credit_score", 650)
    
    # Bureau limit based on credit score
    if credit_score >= 750:
        bureau_multiplier = 0.4
    elif credit_score >= 650:
        bureau_multiplier = 0.3
    elif credit_score >= 550:
        bureau_multiplier = 0.2
    else:
        bureau_multiplier = 0.1
    
    bureau_limit = annual_income * bureau_multiplier
    
    # Eligible amount = min(requested, 30% of annual income, bureau limit)
    eligible_amount = min(requested_amount, annual_income * 0.3, bureau_limit)
    eligible_amount = max(eligible_amount, 50000)  # Minimum ₹50K
    eligible_amount = round(eligible_amount / 10000) * 10000  # Round to nearest 10K
    
    # Interest rate calculation
    base_rate = 11.0
    
    # Risk premium based on risk persona
    risk_persona = llm.get("risk_persona", "moderate_borrower") if isinstance(llm, dict) else "moderate_borrower"
    risk_premiums = {
        "conservative_borrower": 0.0,
        "moderate_borrower": 1.0,
        "first_time_borrower": 1.5,
        "aggressive_borrower": 2.5,
        "distressed_borrower": 4.0,
    }
    risk_premium = risk_premiums.get(risk_persona, 1.0)
    
    # Credit score premium
    if credit_score >= 750:
        score_premium = -0.5
    elif credit_score >= 700:
        score_premium = 0.0
    elif credit_score >= 650:
        score_premium = 0.5
    elif credit_score >= 600:
        score_premium = 1.0
    else:
        score_premium = 2.0
    
    # Fraud premium
    fraud_score = fraud.get("composite_score", 0) if isinstance(fraud, dict) else 0
    if fraud_score <= 20:
        fraud_premium = 0.0
    elif fraud_score <= 40:
        fraud_premium = 0.5
    elif fraud_score <= 60:
        fraud_premium = 1.0
    else:
        fraud_premium = 2.0
    
    interest_rate = round(base_rate + risk_premium + score_premium + fraud_premium, 2)
    interest_rate = min(max(interest_rate, 9.0), 24.0)  # Cap between 9-24%
    
    # EMI table for different tenures
    tenures = [12, 24, 36, 48, 60]
    emi_table = []
    for months in tenures:
        emi = _calculate_emi(eligible_amount, interest_rate, months)
        total_payment = emi * months
        total_interest = total_payment - eligible_amount
        emi_table.append({
            "tenure_months": months,
            "emi": emi,
            "total_payment": round(total_payment, 2),
            "total_interest": round(total_interest, 2),
        })
    
    # Default to 36 months
    default_tenure = 36
    default_emi = _calculate_emi(eligible_amount, interest_rate, default_tenure)
    
    return {
        "offer_id": str(uuid.uuid4()),
        "eligible_amount": eligible_amount,
        "requested_amount": requested_amount,
        "interest_rate": interest_rate,
        "rate_breakdown": {
            "base_rate": base_rate,
            "risk_premium": risk_premium,
            "score_premium": score_premium,
            "fraud_premium": fraud_premium,
        },
        "default_tenure_months": default_tenure,
        "default_emi": default_emi,
        "emi_table": emi_table,
        "risk_persona": risk_persona,
        "credit_score": credit_score,
        "fraud_score": fraud_score,
    }


# ──────────────────────────────────────────────────────────────────
# Negotiation Agent
# ──────────────────────────────────────────────────────────────────

NEGOTIATION_PROMPT = """You are a friendly but professional loan negotiation agent. You've presented a loan offer to the applicant.

Current offer:
- Loan Amount: ₹{amount:,.0f}
- Interest Rate: {rate}% p.a.
- Tenure: {tenure} months
- EMI: ₹{emi:,.0f}/month

The applicant has said: "{objection}"

Negotiation round: {round}/{max_rounds}

Rules:
1. You can adjust the amount by ±20% from current offer (but never exceed original eligible amount)
2. You can adjust tenure between 12-60 months
3. You CANNOT lower the interest rate below {min_rate}%
4. Be empathetic but firm on risk-based pricing
5. If this is the final round, clearly state the final terms

Respond with a JSON object:
{{
  "response_text": "Your conversational response to the applicant (2-3 sentences)",
  "adjusted_offer": {{
    "amount": {amount},
    "rate": {rate},
    "tenure": {tenure},
    "emi": {emi}
  }},
  "is_final": false
}}"""


async def _negotiate(offer: dict, objection: str, round_num: int, max_rounds: int = 3) -> dict:
    """LLM-powered negotiation micro-agent."""
    if not settings.has_groq_key:
        # Mock negotiation
        return {
            "response_text": f"I understand your concern. Let me see what I can do for you. Based on your profile, I can offer you a slightly adjusted tenure. This is round {round_num} of {max_rounds}.",
            "adjusted_offer": {
                "amount": offer["eligible_amount"],
                "rate": offer["interest_rate"],
                "tenure": 48 if round_num == 1 else offer["default_tenure_months"],
                "emi": _calculate_emi(offer["eligible_amount"], offer["interest_rate"], 48 if round_num == 1 else offer["default_tenure_months"]),
            },
            "is_final": round_num >= max_rounds,
        }
    
    try:
        from groq import Groq
        client = Groq(api_key=settings.GROQ_API_KEY)
        
        prompt = NEGOTIATION_PROMPT.format(
            amount=offer["eligible_amount"],
            rate=offer["interest_rate"],
            tenure=offer["default_tenure_months"],
            emi=offer["default_emi"],
            objection=objection,
            round=round_num,
            max_rounds=max_rounds,
            min_rate=offer["interest_rate"] - 0.5,
        )
        
        response = client.chat.completions.create(
            model=settings.GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
            max_tokens=512,
        )
        
        raw = response.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
        
        result = json.loads(raw)
        
        # Recalculate EMI for adjusted offer
        adj = result.get("adjusted_offer", {})
        if adj:
            adj["emi"] = _calculate_emi(
                adj.get("amount", offer["eligible_amount"]),
                adj.get("rate", offer["interest_rate"]),
                adj.get("tenure", offer["default_tenure_months"]),
            )
        
        return result
    except Exception as e:
        return {
            "response_text": f"I appreciate your feedback. Let me review the terms once more.",
            "adjusted_offer": None,
            "is_final": round_num >= max_rounds,
            "error": str(e),
        }


# ──────────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────────

@router.post("/{session_id}/generate")
async def generate_offer(session_id: str):
    """Generate a personalised loan offer based on all pipeline data."""
    session = store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    offer = _generate_offer(session)
    offer["session_id"] = session_id
    offer["status"] = "generated"
    offer["negotiation_rounds"] = 0
    offer["negotiation_log"] = []
    offer["created_at"] = datetime.utcnow().isoformat()
    
    store.update(session_id, {"offer": offer})
    
    # Persist
    try:
        db = await get_db()
        try:
            await db.execute(
                """INSERT INTO offers
                   (id, session_id, eligible_amount, interest_rate, tenure_months,
                    emi_amount, emi_table, status, negotiation_rounds, negotiation_log)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'generated', 0, '[]')""",
                (
                    offer["offer_id"],
                    session_id,
                    offer["eligible_amount"],
                    offer["interest_rate"],
                    offer["default_tenure_months"],
                    offer["default_emi"],
                    json.dumps(offer["emi_table"]),
                ),
            )
            await db.commit()
        finally:
            await db.close()
    except Exception:
        pass
    
    await audit.emit(session_id, "OFFER_GENERATED", "OFFER", {
        "offer_id": offer["offer_id"],
        "amount": offer["eligible_amount"],
        "rate": offer["interest_rate"],
        "emi": offer["default_emi"],
    })
    
    return offer


class NegotiationRequest(BaseModel):
    objection: str

@router.post("/{session_id}/negotiate")
async def negotiate_offer(session_id: str, req: NegotiationRequest):
    """Handle applicant objection via LLM negotiation agent (max 3 rounds)."""
    session = store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    offer = session.get("offer")
    if not offer:
        raise HTTPException(status_code=400, detail="No offer generated yet")
    
    max_rounds = 3
    current_round = offer.get("negotiation_rounds", 0) + 1
    
    if current_round > max_rounds:
        return {
            "session_id": session_id,
            "message": "Maximum negotiation rounds reached. Please accept or decline the current offer.",
            "current_offer": offer,
            "round": current_round - 1,
            "max_rounds": max_rounds,
        }
    
    result = await _negotiate(offer, req.objection, current_round, max_rounds)
    
    # Update offer with negotiation
    negotiation_log = offer.get("negotiation_log", [])
    negotiation_log.append({
        "round": current_round,
        "objection": req.objection,
        "response": result.get("response_text"),
        "adjusted_offer": result.get("adjusted_offer"),
        "timestamp": datetime.utcnow().isoformat(),
    })
    
    updated_offer = {**offer}
    if result.get("adjusted_offer"):
        adj = result["adjusted_offer"]
        updated_offer["eligible_amount"] = adj.get("amount", offer["eligible_amount"])
        updated_offer["interest_rate"] = adj.get("rate", offer["interest_rate"])
        updated_offer["default_tenure_months"] = adj.get("tenure", offer["default_tenure_months"])
        updated_offer["default_emi"] = adj.get("emi", offer["default_emi"])
    
    updated_offer["negotiation_rounds"] = current_round
    updated_offer["negotiation_log"] = negotiation_log
    
    store.update(session_id, {"offer": updated_offer})
    
    await audit.emit(session_id, "OFFER_NEGOTIATED", "OFFER", {
        "round": current_round,
        "objection": req.objection[:100],
        "adjusted": result.get("adjusted_offer") is not None,
    })
    
    return {
        "session_id": session_id,
        "response": result.get("response_text"),
        "adjusted_offer": result.get("adjusted_offer"),
        "round": current_round,
        "max_rounds": max_rounds,
        "is_final": result.get("is_final", False),
        "current_offer": updated_offer,
    }


@router.post("/{session_id}/accept")
async def accept_offer(session_id: str):
    """Accept the current offer and finalize terms."""
    session = store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    offer = session.get("offer")
    if not offer:
        raise HTTPException(status_code=400, detail="No offer to accept")
    
    accepted_at = datetime.utcnow().isoformat()
    offer["status"] = "accepted"
    offer["accepted_at"] = accepted_at
    
    store.update(session_id, {"offer": offer, "status": "completed"})
    
    # Persist
    try:
        db = await get_db()
        try:
            await db.execute(
                """UPDATE offers SET status = 'accepted', accepted_at = ?,
                   negotiation_rounds = ?, negotiation_log = ? WHERE id = ?""",
                (
                    accepted_at,
                    offer.get("negotiation_rounds", 0),
                    json.dumps(offer.get("negotiation_log", [])),
                    offer["offer_id"],
                ),
            )
            await db.execute(
                "UPDATE sessions SET status = 'completed', updated_at = datetime('now') WHERE id = ?",
                (session_id,),
            )
            await db.commit()
        finally:
            await db.close()
    except Exception:
        pass
    
    await audit.emit(session_id, "OFFER_ACCEPTED", "OFFER", {
        "offer_id": offer["offer_id"],
        "amount": offer["eligible_amount"],
        "rate": offer["interest_rate"],
        "tenure": offer["default_tenure_months"],
        "emi": offer["default_emi"],
        "negotiation_rounds": offer.get("negotiation_rounds", 0),
    })
    
    return {
        "session_id": session_id,
        "status": "accepted",
        "offer": offer,
        "accepted_at": accepted_at,
    }


@router.post("/{session_id}/decline")
async def decline_offer(session_id: str):
    """Decline the offer."""
    session = store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    offer = session.get("offer", {})
    offer["status"] = "declined"
    store.update(session_id, {"offer": offer, "status": "declined"})
    
    await audit.emit(session_id, "OFFER_DECLINED", "OFFER", {})
    return {"session_id": session_id, "status": "declined"}
