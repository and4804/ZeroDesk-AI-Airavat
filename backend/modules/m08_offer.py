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
from models.llm_responses import NegotiationResponse

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
    
    # EMI table for all available tenures
    emi_table = []
    for months in _TENURE_OPTIONS:
        emi = _calculate_emi(eligible_amount, interest_rate, months)
        total_payment = emi * months
        total_interest = total_payment - eligible_amount
        emi_table.append({
            "tenure_months": months,
            "tenure_years": round(months / 12, 1),
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

_TENURE_OPTIONS = [12, 24, 36, 48, 60, 72, 84]  # months available to offer
_MAX_TENURE = 84
_MIN_TENURE = 12

NEGOTIATION_PROMPT = """You are a professional loan advisor at a bank. Your goal is to help the applicant find loan terms they can accept while staying within bank policy.

CURRENT OFFER:
- Loan Amount : ₹{amount:,}
- Interest Rate: {rate}% p.a.
- Tenure       : {tenure} months  ({tenure_years} years)
- Monthly EMI  : ₹{emi:,.0f}
- Credit Score : {credit_score}
- Risk Profile : {risk_persona}

BANK POLICY LIMITS (HARD — never violate):
- Rate floor  : {min_rate}% — NEVER quote a rate below this
- Rate ceiling: 24%
- Min tenure  : {min_tenure} months
- Max tenure  : {max_tenure} months ({max_tenure_years} years)
- Loan amount : cannot be increased; current max is ₹{amount:,}

EMI TABLE at current rate {rate}% for this amount:
{tenure_table}

INTENT DETECTION — read the applicant's message and respond accordingly:

► If they ask to EXTEND TENURE / MORE YEARS / REDUCE EMI by stretching:
  • Propose a longer tenure from the EMI table above.
  • Pick the next sensible step up (e.g. if current is 36 mo, suggest 48 or 60).
  • State the new tenure in BOTH months AND years, and the new lower EMI clearly.
  • Max allowed: {max_tenure} months ({max_tenure_years} years).

► If they ask for LOWER RATE / REDUCE INTEREST:
  • Round 1: offer 0.25% goodwill discount if not already applied (floor: {min_rate}%).
  • Round 2: offer another 0.25% if still above floor. Mention credit score justification.
  • Round 3+: explain rate is already competitive; pivot to tenure extension instead.

► If they ask for MORE MONEY / HIGHER AMOUNT:
  • Explain the amount is set by income + credit policy (max ₹{amount:,}).
  • Offer to make the current amount more affordable by extending tenure.

► If they express vague dissatisfaction:
  • Ask which is the bigger concern — the monthly EMI or the total cost — then address it.

Negotiation round : {round_num}
Previous history  :
{history}

Applicant said: "{objection}"

Rules:
- Response: 2-3 conversational sentences. Warm but professional.
- ALWAYS recalculate EMI correctly when changing tenure or rate.
- Only change what the applicant asked to change.
- Do NOT set adjusted_offer if nothing changes.

Respond ONLY with valid JSON (no markdown, no extra text):
{{
  "response_text": "Your warm 2-3 sentence response",
  "adjusted_offer": {{
    "amount": {amount},
    "rate": <new rate as a number, respecting floor/ceiling>,
    "tenure": <new tenure in months, between {min_tenure} and {max_tenure}>,
    "emi": <recalculated EMI>
  }},
  "is_final": false
}}
Set "adjusted_offer" to null if nothing about the offer is changing."""


def _build_tenure_table(amount: float, rate: float, current_tenure: int) -> str:
    """Build a plain-text EMI table for all available tenures."""
    lines = []
    for t in _TENURE_OPTIONS:
        emi = _calculate_emi(amount, rate, t)
        marker = "  ← current" if t == current_tenure else ""
        years = t // 12
        extra = f" ({years} yr)" if years >= 1 else ""
        lines.append(f"  {t:3d} months{extra}: ₹{emi:,.0f}/mo{marker}")
    return "\n".join(lines)


def _mock_negotiate(offer: dict, objection: str, round_num: int, min_rate: float) -> dict:
    """
    Rule-based fallback when no Groq key is available.
    Detects intent (tenure vs rate vs amount) from keywords.
    """
    import re
    obj_lower = objection.lower()
    amount = offer["eligible_amount"]
    rate = offer["interest_rate"]
    tenure = offer["default_tenure_months"]

    # ── Tenure extension intent ──────────────────────────────────
    tenure_kw = re.search(
        r"\b(extend|longer|more years?|increase tenure|higher tenure|"
        r"(\d+)\s*year|(\d+)\s*yr|reduce emi|lower emi|smaller emi|monthly)\b",
        obj_lower,
    )
    # Explicit year mention: "5 years", "60 months"
    year_match = re.search(r"\b(\d+)\s*year", obj_lower)
    month_match = re.search(r"\b(\d+)\s*month", obj_lower)

    if year_match:
        requested_months = int(year_match.group(1)) * 12
        new_tenure = max(_MIN_TENURE, min(_MAX_TENURE, requested_months))
    elif month_match:
        requested_months = int(month_match.group(1))
        new_tenure = max(_MIN_TENURE, min(_MAX_TENURE, requested_months))
    elif tenure_kw:
        # Pick next step up from current tenure
        options_above = [t for t in _TENURE_OPTIONS if t > tenure]
        new_tenure = options_above[0] if options_above else _MAX_TENURE
    else:
        new_tenure = None

    if new_tenure and new_tenure != tenure:
        new_emi = _calculate_emi(amount, rate, new_tenure)
        years_label = f"{new_tenure // 12} year{'s' if new_tenure // 12 != 1 else ''}"
        return {
            "response_text": (
                f"Absolutely! I can extend your tenure to {new_tenure} months ({years_label}), "
                f"which brings your EMI down to ₹{new_emi:,.0f}/month at the same {rate}% rate. "
                f"That's well within our maximum tenure of {_MAX_TENURE} months."
            ),
            "adjusted_offer": {
                "amount": amount,
                "rate": rate,
                "tenure": new_tenure,
                "emi": new_emi,
            },
            "is_final": False,
        }

    # ── Rate reduction intent ────────────────────────────────────
    if round_num <= 2:
        new_rate = max(rate - 0.25, min_rate)
        new_emi = _calculate_emi(amount, new_rate, tenure)
        if new_rate < rate:
            return {
                "response_text": (
                    f"I understand your concern — let me see what I can do. "
                    f"I can bring the rate down to {new_rate}%, making your EMI ₹{new_emi:,.0f}/month. "
                    f"We can also extend the tenure up to {_MAX_TENURE} months if you'd like a lower EMI."
                ),
                "adjusted_offer": {
                    "amount": amount, "rate": new_rate,
                    "tenure": tenure, "emi": new_emi,
                },
                "is_final": False,
            }

    # ── Round 3+ fallback ────────────────────────────────────────
    next_tenure = next((t for t in _TENURE_OPTIONS if t > tenure), _MAX_TENURE)
    next_emi = _calculate_emi(amount, rate, next_tenure)
    return {
        "response_text": (
            f"The rate of {rate}% is already the most competitive I can offer for your profile. "
            f"However, I can extend your tenure to {next_tenure} months, which would reduce your EMI to ₹{next_emi:,.0f}/month — "
            f"would that work for you?"
        ),
        "adjusted_offer": None,
        "is_final": False,
    }


async def _negotiate(offer: dict, objection: str, round_num: int, max_rounds: int = 999) -> dict:
    """LLM-powered negotiation micro-agent with intent-aware strategy."""

    original_rate = offer.get("rate_breakdown", {}).get("base_rate", offer["interest_rate"])
    min_rate = max(original_rate - 1.0, 9.0)  # max 1% total discount
    credit_score = offer.get("credit_score", 650)
    risk_persona = offer.get("risk_persona", "moderate_borrower")
    amount = offer["eligible_amount"]
    rate = offer["interest_rate"]
    tenure = offer["default_tenure_months"]
    emi = offer["default_emi"]

    # Build history
    history_lines = []
    for entry in offer.get("negotiation_log", []):
        history_lines.append(
            f"  Round {entry.get('round', '?')}: "
            f"User: \"{entry.get('objection', '')}\" "
            f"→ AI: \"{entry.get('response', '')[:120]}...\""
        )
    history = "\n".join(history_lines) if history_lines else "  (First round)"

    if not settings.has_groq_key:
        return _mock_negotiate(offer, objection, round_num, min_rate)

    try:
        from groq import Groq
        client = Groq(api_key=settings.GROQ_API_KEY)

        tenure_table = _build_tenure_table(amount, rate, tenure)

        prompt = NEGOTIATION_PROMPT.format(
            amount=int(amount),
            rate=rate,
            tenure=tenure,
            tenure_years=round(tenure / 12, 1),
            emi=emi,
            credit_score=credit_score,
            risk_persona=risk_persona,
            original_rate=original_rate,
            min_rate=min_rate,
            min_tenure=_MIN_TENURE,
            max_tenure=_MAX_TENURE,
            max_tenure_years=_MAX_TENURE // 12,
            tenure_table=tenure_table,
            objection=objection,
            round_num=round_num,
            history=history,
        )

        response = client.chat.completions.create(
            model=settings.GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
            max_tokens=600,
        )

        raw = response.choices[0].message.content.strip()
        validated = NegotiationResponse.from_raw(raw)
        result = validated.model_dump()

        # Server-side enforcement — always recompute EMI and enforce policy
        adj = result.get("adjusted_offer")
        if adj and isinstance(adj, dict):
            new_rate = max(min(adj.get("rate") or rate, 24.0), min_rate)
            new_tenure = max(min(int(adj.get("tenure") or tenure), _MAX_TENURE), _MIN_TENURE)
            new_amount = adj.get("amount") or amount
            adj["rate"] = round(new_rate, 2)
            adj["tenure"] = new_tenure
            adj["amount"] = new_amount
            adj["emi"] = _calculate_emi(new_amount, new_rate, new_tenure)

        return result

    except Exception as e:
        return _mock_negotiate(offer, objection, round_num, min_rate)


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
            
            # Regenerate EMI table with updated rate/amount/tenure
            new_amount = updated_offer["eligible_amount"]
            new_rate = updated_offer["interest_rate"]
            emi_table = []
            for months in _TENURE_OPTIONS:
                emi_val = _calculate_emi(new_amount, new_rate, months)
                total_payment = emi_val * months
                total_interest = total_payment - new_amount
                emi_table.append({
                    "tenure_months": months,
                    "tenure_years": round(months / 12, 1),
                    "emi": round(emi_val, 2),
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
            "policy": {
                "min_rate": max(updated_offer.get("rate_breakdown", {}).get("base_rate", updated_offer["interest_rate"]) - 1.0, 9.0),
                "min_tenure_months": _MIN_TENURE,
                "max_tenure_months": _MAX_TENURE,
                "max_tenure_years": _MAX_TENURE // 12,
            },
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
