"""
M10 — Compliance Dashboard, Audit Repository & Regulatory Report Generation
Back-office APIs for session viewing, analytics, and audit report generation.
"""

import json
import hashlib
from datetime import datetime
from fastapi import APIRouter, HTTPException
from typing import Optional

from config import settings
from database import get_db
from session_store import store
from events import audit

router = APIRouter(prefix="/api/compliance", tags=["M10 - Compliance"])


# ──────────────────────────────────────────────────────────────────
# Session Listing
# ──────────────────────────────────────────────────────────────────

@router.get("/sessions")
async def list_all_sessions(status: Optional[str] = None, limit: int = 50):
    """List all sessions with status, fraud scores, and consent data."""
    db = await get_db()
    try:
        query = """
            SELECT s.*,
                   fs.composite_score as fraud_score,
                   fs.risk_level as fraud_risk_level,
                   cr.phrase_detected as consent_phrase,
                   cr.segment_hash as consent_hash,
                   cr.is_consent,
                   o.eligible_amount as offer_amount,
                   o.status as offer_status,
                   ps.current_stage as pipeline_stage
            FROM sessions s
            LEFT JOIN fraud_scores fs ON s.id = fs.session_id
            LEFT JOIN consent_records cr ON s.id = cr.session_id
            LEFT JOIN offers o ON s.id = o.session_id
            LEFT JOIN pipeline_states ps ON s.id = ps.session_id
        """
        params = []
        
        if status:
            query += " WHERE s.status = ?"
            params.append(status)
        
        query += " ORDER BY s.created_at DESC LIMIT ?"
        params.append(limit)
        
        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()
        
        sessions = []
        for row in rows:
            session = dict(row)
            # Parse geolocation JSON
            if session.get("geolocation"):
                try:
                    session["geolocation"] = json.loads(session["geolocation"])
                except (json.JSONDecodeError, TypeError):
                    pass
            sessions.append(session)
        
        return {"sessions": sessions, "total": len(sessions)}
    finally:
        await db.close()


# ──────────────────────────────────────────────────────────────────
# Session Detail
# ──────────────────────────────────────────────────────────────────

@router.get("/sessions/{session_id}")
async def get_session_detail(session_id: str):
    """Get comprehensive session detail with all tier data."""
    db = await get_db()
    try:
        # Session
        cursor = await db.execute("SELECT * FROM sessions WHERE id = ?", (session_id,))
        session = await cursor.fetchone()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        session = dict(session)
        
        # Transcript
        cursor = await db.execute(
            "SELECT * FROM transcripts WHERE session_id = ? ORDER BY segment_index", (session_id,)
        )
        transcripts = [dict(r) for r in await cursor.fetchall()]
        
        # Extracted fields
        cursor = await db.execute(
            "SELECT * FROM extracted_fields WHERE session_id = ?", (session_id,)
        )
        fields = [dict(r) for r in await cursor.fetchall()]
        
        # Consent
        cursor = await db.execute(
            "SELECT * FROM consent_records WHERE session_id = ?", (session_id,)
        )
        consent = [dict(r) for r in await cursor.fetchall()]
        
        # Vision
        cursor = await db.execute(
            "SELECT * FROM vision_results WHERE session_id = ? ORDER BY frame_index", (session_id,)
        )
        vision = [dict(r) for r in await cursor.fetchall()]
        
        # LLM Assessment
        cursor = await db.execute(
            "SELECT * FROM llm_assessments WHERE session_id = ?", (session_id,)
        )
        llm_row = await cursor.fetchone()
        llm = dict(llm_row) if llm_row else None
        if llm:
            llm["reasoning_trace"] = json.loads(llm.get("reasoning_trace", "[]"))
            llm["contradictions"] = json.loads(llm.get("contradictions", "[]"))
        
        # Fraud
        cursor = await db.execute(
            "SELECT * FROM fraud_scores WHERE session_id = ?", (session_id,)
        )
        fraud_row = await cursor.fetchone()
        fraud = dict(fraud_row) if fraud_row else None
        if fraud:
            fraud["signal_breakdown"] = json.loads(fraud.get("signal_breakdown", "{}"))
        
        # Bureau
        cursor = await db.execute(
            "SELECT * FROM bureau_results WHERE session_id = ?", (session_id,)
        )
        bureau_row = await cursor.fetchone()
        bureau = dict(bureau_row) if bureau_row else None
        if bureau:
            bureau["dpd_history"] = json.loads(bureau.get("dpd_history", "[]"))
            bureau["rule_evaluations"] = json.loads(bureau.get("rule_evaluations", "[]"))
        
        # Offer
        cursor = await db.execute(
            "SELECT * FROM offers WHERE session_id = ?", (session_id,)
        )
        offer_row = await cursor.fetchone()
        offer = dict(offer_row) if offer_row else None
        if offer:
            offer["emi_table"] = json.loads(offer.get("emi_table", "[]"))
            offer["negotiation_log"] = json.loads(offer.get("negotiation_log", "[]"))
        
        # Pipeline state
        cursor = await db.execute(
            "SELECT * FROM pipeline_states WHERE session_id = ?", (session_id,)
        )
        pipeline_row = await cursor.fetchone()
        pipeline = dict(pipeline_row) if pipeline_row else None
        if pipeline:
            pipeline["stages_completed"] = json.loads(pipeline.get("stages_completed", "[]"))
            pipeline["stages_failed"] = json.loads(pipeline.get("stages_failed", "[]"))
        
        # Audit events
        cursor = await db.execute(
            "SELECT * FROM audit_events WHERE session_id = ? ORDER BY timestamp", (session_id,)
        )
        events = []
        for r in await cursor.fetchall():
            e = dict(r)
            e["data"] = json.loads(e.get("data", "{}"))
            events.append(e)
        
        return {
            "session": session,
            "transcript": {
                "segments": transcripts,
                "full_text": " ".join(t["text"] for t in transcripts),
            },
            "extracted_fields": fields,
            "consent": consent,
            "vision": vision,
            "llm_assessment": llm,
            "fraud": fraud,
            "bureau": bureau,
            "offer": offer,
            "pipeline": pipeline,
            "audit_events": events,
            "event_count": len(events),
        }
    finally:
        await db.close()


# ──────────────────────────────────────────────────────────────────
# Audit Report Generation
# ──────────────────────────────────────────────────────────────────

@router.get("/sessions/{session_id}/report")
async def generate_audit_report(session_id: str):
    """
    Generate a machine-readable regulatory audit report.
    Contains all required compliance data from a single session.
    Reconstructable from stored audit logs alone.
    """
    detail = await get_session_detail(session_id)
    
    # Compute transcript hash
    full_text = detail["transcript"]["full_text"]
    transcript_hash = hashlib.sha256(full_text.encode("utf-8")).hexdigest() if full_text else None
    
    report = {
        "report_type": "regulatory_audit",
        "version": "1.0",
        "generated_at": datetime.utcnow().isoformat(),
        "session_reference": {
            "session_id": session_id,
            "created_at": detail["session"].get("created_at"),
            "status": detail["session"].get("status"),
            "device_fingerprint": detail["session"].get("device_fingerprint"),
            "ip_address": detail["session"].get("ip_address"),
        },
        "transcript": {
            "hash_algorithm": "SHA-256",
            "transcript_hash": transcript_hash,
            "segment_count": len(detail["transcript"]["segments"]),
        },
        "consent_trail": {
            "records": detail["consent"],
            "consent_obtained": any(c.get("is_consent", False) for c in detail["consent"]) if detail["consent"] else False,
        },
        "identity_verification": {
            "liveness_frames_analyzed": len(detail["vision"]),
            "liveness_confirmed": any(v.get("is_live") for v in detail["vision"]) if detail["vision"] else False,
            "age_estimates": [v.get("estimated_age") for v in detail["vision"] if v.get("estimated_age")],
        },
        "risk_assessment": {
            "llm_assessment": detail["llm_assessment"],
            "fraud_scoring": {
                "composite_score": detail["fraud"].get("composite_score") if detail["fraud"] else None,
                "risk_level": detail["fraud"].get("risk_level") if detail["fraud"] else None,
                "signal_breakdown": detail["fraud"].get("signal_breakdown") if detail["fraud"] else None,
            },
        },
        "bureau_decision": {
            "credit_score": detail["bureau"].get("credit_score") if detail["bureau"] else None,
            "policy_decision": detail["bureau"].get("policy_decision") if detail["bureau"] else None,
            "policy_explanation": detail["bureau"].get("policy_explanation") if detail["bureau"] else None,
            "rule_evaluations": detail["bureau"].get("rule_evaluations") if detail["bureau"] else None,
        },
        "offer_terms": {
            "eligible_amount": detail["offer"].get("eligible_amount") if detail["offer"] else None,
            "interest_rate": detail["offer"].get("interest_rate") if detail["offer"] else None,
            "tenure_months": detail["offer"].get("tenure_months") if detail["offer"] else None,
            "emi": detail["offer"].get("emi_amount") if detail["offer"] else None,
            "status": detail["offer"].get("status") if detail["offer"] else None,
            "accepted_at": detail["offer"].get("accepted_at") if detail["offer"] else None,
            "negotiation_rounds": detail["offer"].get("negotiation_rounds") if detail["offer"] else 0,
        },
        "pipeline_trace": {
            "stages_completed": detail["pipeline"].get("stages_completed") if detail["pipeline"] else [],
            "stages_failed": detail["pipeline"].get("stages_failed") if detail["pipeline"] else [],
            "final_stage": detail["pipeline"].get("current_stage") if detail["pipeline"] else None,
        },
        "audit_event_count": detail["event_count"],
        "audit_events": detail["audit_events"],
    }
    
    # Sign the report
    report_json = json.dumps(report, sort_keys=True, default=str)
    report["report_hash"] = hashlib.sha256(report_json.encode("utf-8")).hexdigest()
    
    return report


# ──────────────────────────────────────────────────────────────────
# Analytics
# ──────────────────────────────────────────────────────────────────

@router.get("/analytics")
async def get_analytics():
    """
    Get aggregate analytics for the dashboard:
    - Total sessions, completion rate
    - Fraud score distribution
    - Offer acceptance rate
    - Pipeline drop-off funnel
    """
    db = await get_db()
    try:
        # Total sessions by status
        cursor = await db.execute(
            "SELECT status, COUNT(*) as count FROM sessions GROUP BY status"
        )
        status_counts = {row["status"]: row["count"] for row in await cursor.fetchall()}
        
        # Fraud distribution
        cursor = await db.execute(
            "SELECT risk_level, COUNT(*) as count FROM fraud_scores GROUP BY risk_level"
        )
        fraud_dist = {row["risk_level"]: row["count"] for row in await cursor.fetchall()}
        
        # Offer stats
        cursor = await db.execute(
            "SELECT status, COUNT(*) as count FROM offers GROUP BY status"
        )
        offer_stats = {row["status"]: row["count"] for row in await cursor.fetchall()}
        
        # Pipeline funnel
        cursor = await db.execute(
            "SELECT current_stage, COUNT(*) as count FROM pipeline_states GROUP BY current_stage"
        )
        funnel = {row["current_stage"]: row["count"] for row in await cursor.fetchall()}
        
        # Consent stats
        cursor = await db.execute(
            "SELECT is_consent, COUNT(*) as count FROM consent_records GROUP BY is_consent"
        )
        consent_stats = {}
        for row in await cursor.fetchall():
            key = "granted" if row["is_consent"] else "denied"
            consent_stats[key] = row["count"]
        
        # Average fraud score
        cursor = await db.execute(
            "SELECT AVG(composite_score) as avg_score FROM fraud_scores"
        )
        row = await cursor.fetchone()
        avg_fraud = round(row["avg_score"], 2) if row and row["avg_score"] else 0
        
        total_sessions = sum(status_counts.values())
        completed = status_counts.get("completed", 0)
        
        return {
            "total_sessions": total_sessions,
            "completion_rate": round(completed / total_sessions * 100, 1) if total_sessions > 0 else 0,
            "session_status": status_counts,
            "fraud_distribution": fraud_dist,
            "average_fraud_score": avg_fraud,
            "offer_stats": offer_stats,
            "acceptance_rate": round(
                offer_stats.get("accepted", 0) / sum(offer_stats.values()) * 100, 1
            ) if offer_stats else 0,
            "consent_stats": consent_stats,
            "pipeline_funnel": funnel,
        }
    finally:
        await db.close()
