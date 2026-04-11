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
    
    # Confidence metric — calculated but NOT applied to initial rate (only during negotiation)
    avg_confidence = 0.0
    confidence_count = 0
    for field_data in fields.values():
        if isinstance(field_data, dict) and field_data.get("value"):
            avg_confidence += field_data.get("confidence", 0)
            confidence_count += 1
    avg_confidence = avg_confidence / confidence_count if confidence_count > 0 else 0
    
    # Confidence discount is NOT applied upfront — only used as leverage during negotiation
    confidence_discount = 0.0
    
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
            "confidence_discount": confidence_discount,
        },
        "avg_confidence": round(avg_confidence, 3),
        "confidence_discount": confidence_discount,
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

NEGOTIATION_PROMPT = """You are an expert, persuasive loan negotiation agent for a bank. You must convince the applicant to accept the current loan offer.

Current offer:
- Loan Amount: {amount}
- Interest Rate: {rate}% p.a.
- Tenure: {tenure} months
- EMI: {emi}/month
- Credit Score: {credit_score}
- Risk Profile: {risk_persona}

Original offer rate: {original_rate}%
Minimum allowed rate: {min_rate}% (NEVER go below this)

Negotiation round: {round_num}
Previous negotiation history:
{history}

The applicant just said: "{objection}"

STRATEGY (follow strictly based on round number):
- Round 1: Acknowledge concern warmly. Offer a SMALL discount of 0.25% as a goodwill gesture. Say something like "I understand, let me see what I can do..."
- Round 2: If they push again, offer another 0.25% discount (if still above min_rate). Explain why: mention their credit score, risk profile, and market benchmark rates.
- Round 3+: DO NOT offer any more discounts. Instead, CONVINCE the user by:
  * Explaining the rate is already competitive for their credit profile (credit score {credit_score})
  * Comparing to market rates (typical personal loan: 12-24%, home loan: 8.5-12%)
  * Highlighting the benefit of the loan (achieving their goal)
  * Offering flexible tenure instead (longer tenure = lower EMI)
  * Mentioning they can refinance later when credit score improves
  * Being empathetic but firm

IMPORTANT: Keep responses SHORT (2-3 sentences max). Be conversational, not robotic. Never repeat the same argument twice.

Respond ONLY with valid JSON:
{{
  "response_text": "Your conversational response (2-3 sentences)",
  "adjusted_offer": {{
    "amount": {amount},
    "rate": {rate},
    "tenure": {tenure},
    "emi": {emi}
  }},
  "is_final": false
}}"""


async def _negotiate(offer: dict, objection: str, round_num: int, max_rounds: int = 999) -> dict:
    """LLM-powered negotiation micro-agent with 3-phase strategy."""
    
    original_rate = offer.get("rate_breakdown", {}).get("base_rate", offer["interest_rate"])
    min_rate = max(original_rate - 1.0, 9.0)  # Can only discount up to 1% total
    credit_score = offer.get("credit_score", 650)
    risk_persona = offer.get("risk_persona", "moderate_borrower")
    
    # Build history from negotiation log
    history_lines = []
    for entry in offer.get("negotiation_log", []):
        history_lines.append(f"  Round {entry.get('round', '?')}: User said: \"{entry.get('objection', '')}\" → AI responded: \"{entry.get('response', '')[:100]}...\"")
    history = "\n".join(history_lines) if history_lines else "  (First negotiation round)"
    
    if not settings.has_groq_key:
        # Mock negotiation
        if round_num == 1:
            new_rate = max(offer["interest_rate"] - 0.25, min_rate)
            new_emi = _calculate_emi(offer["eligible_amount"], new_rate, offer["default_tenure_months"])
            return {
                "response_text": f"I understand your concern. Let me see what I can do — I can bring your rate down to {new_rate}%. That would make your EMI ₹{new_emi:,.0f}. Shall we proceed with this?",
                "adjusted_offer": {
                    "amount": offer["eligible_amount"],
                    "rate": new_rate,
                    "tenure": offer["default_tenure_months"],
                    "emi": new_emi,
                },
                "is_final": False,
            }
        else:
            return {
                "response_text": f"I've already given you the best possible rate for your credit profile. This is genuinely competitive compared to market rates of 14-18% for similar profiles. Shall I extend the tenure to reduce your EMI instead?",
                "adjusted_offer": None,
                "is_final": False,
            }
    
    try:
        from groq import Groq
        client = Groq(api_key=settings.GROQ_API_KEY)
        
        prompt = NEGOTIATION_PROMPT.format(
            amount=offer["eligible_amount"],
            rate=offer["interest_rate"],
            tenure=offer["default_tenure_months"],
            emi=offer["default_emi"],
            credit_score=credit_score,
            risk_persona=risk_persona,
            original_rate=original_rate,
            min_rate=min_rate,
            objection=objection,
            round_num=round_num,
            history=history,
        )
        
        response = client.chat.completions.create(
            model=settings.GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.6,
            max_tokens=512,
        )
        
        raw = response.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        
        result = None
        try:
            result = json.loads(raw)
        except json.JSONDecodeError:
            import re
            json_match = re.search(r'\{.*\}', raw, re.DOTALL)
            if json_match:
                try:
                    result = json.loads(json_match.group())
                except json.JSONDecodeError:
                    pass
        
        if not result:
            result = {
                "response_text": raw.split('{')[0].strip() or "I understand your concern. This rate reflects your current credit profile, and I've already applied the best terms I can offer.",
                "adjusted_offer": None,
                "is_final": False,
            }
        
        # Recalculate EMI for adjusted offer
        adj = result.get("adjusted_offer")
        if adj and isinstance(adj, dict):
            # Enforce min rate
            if adj.get("rate", 999) < min_rate:
                adj["rate"] = min_rate
            adj["emi"] = _calculate_emi(
                adj.get("amount", offer["eligible_amount"]),
                adj.get("rate", offer["interest_rate"]),
                adj.get("tenure", offer["default_tenure_months"]),
            )
        
        return result
    except Exception as e:
        return {
            "response_text": "I appreciate your feedback. Let me review the terms once more.",
            "adjusted_offer": None,
            "is_final": False,
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
    """Handle applicant objection via LLM negotiation agent."""
    try:
        session = store.get(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        offer = session.get("offer")
        if not offer:
            raise HTTPException(status_code=400, detail="No offer generated yet")
        
        current_round = offer.get("negotiation_rounds", 0) + 1
        
        result = await _negotiate(offer, req.objection, current_round, max_rounds=999)
        
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
            
            # Regenerate EMI table with updated rate/amount
            new_amount = updated_offer["eligible_amount"]
            new_rate = updated_offer["interest_rate"]
            tenures = [12, 24, 36, 48, 60]
            emi_table = []
            for months in tenures:
                emi = _calculate_emi(new_amount, new_rate, months)
                total_payment = emi * months
                total_interest = total_payment - new_amount
                emi_table.append({
                    "tenure_months": months,
                    "emi": round(emi, 2),
                    "total_payment": round(total_payment, 2),
                    "total_interest": round(total_interest, 2),
                })
            updated_offer["emi_table"] = emi_table
        
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
            "max_rounds": 999,
            "is_final": result.get("is_final", False),
            "current_offer": updated_offer,
        }
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


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
