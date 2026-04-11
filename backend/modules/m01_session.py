"""
M01 — Session Management
Handles session creation, token validation, device fingerprinting, and metadata storage.
"""

import uuid
import json
import jwt
import httpx
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional

from config import settings
from database import get_db
from session_store import store
from events import audit

router = APIRouter(prefix="/api/sessions", tags=["M01 - Sessions"])


# ──────────────────────────────────────────────────────────────────
# Models
# ──────────────────────────────────────────────────────────────────

class SessionCreateRequest(BaseModel):
    applicant_name: Optional[str] = None
    applicant_id: Optional[str] = None

class SessionMetadataRequest(BaseModel):
    device_fingerprint: str
    user_agent: str
    screen_resolution: Optional[str] = None
    timezone: Optional[str] = None
    language: Optional[str] = None
    platform: Optional[str] = None
    webrtc_supported: Optional[bool] = None
    canvas_hash: Optional[str] = None
    browser_geo_lat: Optional[float] = None
    browser_geo_lng: Optional[float] = None


# ──────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────

def _create_token(session_id: str) -> str:
    payload = {
        "session_id": session_id,
        "exp": datetime.utcnow() + timedelta(minutes=settings.JWT_EXPIRY_MINUTES),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def _validate_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Session token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid session token")


async def _get_geolocation(ip: str) -> dict:
    """Get geolocation from IP using free API."""
    if ip in ("127.0.0.1", "::1", "localhost"):
        return {"city": "Local", "country": "Local", "lat": 0, "lon": 0, "isp": "localhost"}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{settings.GEOIP_API_URL}/{ip}")
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "city": data.get("city", "Unknown"),
                    "region": data.get("regionName", "Unknown"),
                    "country": data.get("country", "Unknown"),
                    "lat": data.get("lat", 0),
                    "lon": data.get("lon", 0),
                    "isp": data.get("isp", "Unknown"),
                    "is_proxy": data.get("proxy", False),
                    "is_hosting": data.get("hosting", False),
                }
    except Exception:
        pass
    return {"city": "Unknown", "country": "Unknown", "lat": 0, "lon": 0}


# ──────────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────────

@router.post("/create")
async def create_session(req: SessionCreateRequest):
    """Create a new session and return a tokenised link."""
    session_id = str(uuid.uuid4())
    token = _create_token(session_id)
    expires_at = (datetime.utcnow() + timedelta(minutes=settings.JWT_EXPIRY_MINUTES)).isoformat()
    
    # Persist to SQLite
    db = await get_db()
    try:
        await db.execute(
            """INSERT INTO sessions (id, token, status, applicant_name, applicant_id)
               VALUES (?, ?, 'created', ?, ?)""",
            (session_id, token, req.applicant_name, req.applicant_id),
        )
        await db.commit()
    finally:
        await db.close()
    
    # In-memory state
    store.create(session_id, {
        "applicant_name": req.applicant_name,
        "applicant_id": req.applicant_id,
        "expires_at": expires_at,
    })
    
    # Audit event
    await audit.emit(session_id, "SESSION_CREATED", "SESSION_INIT", {
        "applicant_name": req.applicant_name,
        "applicant_id": req.applicant_id,
    })
    
    return {
        "session_id": session_id,
        "token": token,
        "join_url": f"{settings.FRONTEND_URL}/session/{session_id}?token={token}",
        "expires_at": expires_at,
        "expires_in_minutes": settings.JWT_EXPIRY_MINUTES,
    }


@router.get("/{session_id}")
async def get_session(session_id: str):
    """Get session details."""
    session = store.get(session_id)
    if not session:
        # Try loading from DB
        db = await get_db()
        try:
            cursor = await db.execute("SELECT * FROM sessions WHERE id = ?", (session_id,))
            row = await cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Session not found")
            return dict(row)
        finally:
            await db.close()
    return session


@router.get("/{session_id}/validate")
async def validate_session(session_id: str, token: str):
    """Validate a session token."""
    payload = _validate_token(token)
    if payload["session_id"] != session_id:
        raise HTTPException(status_code=403, detail="Token does not match session")
    # Include current pipeline stage per doc spec
    session = store.get(session_id)
    stage = session.get("pipeline_stage", "SESSION_INIT") if session else "SESSION_INIT"
    return {"valid": True, "session_id": session_id, "stage": stage}


@router.post("/{session_id}/metadata")
async def store_metadata(session_id: str, req: SessionMetadataRequest, request: Request):
    """Store device fingerprint, IP, geolocation, and other session metadata."""
    session = store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Get client IP
    ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else "unknown")
    if "," in ip:
        ip = ip.split(",")[0].strip()
    
    # Get geolocation — prefer browser GPS if provided, fallback to IP-based
    if req.browser_geo_lat is not None and req.browser_geo_lng is not None:
        geo = {
            "city": "Browser GPS",
            "country": "Unknown",
            "lat": req.browser_geo_lat,
            "lon": req.browser_geo_lng,
            "source": "browser_geolocation",
        }
        # Also fetch IP geo for fraud comparison later
        ip_geo = await _get_geolocation(ip)
        geo["ip_city"] = ip_geo.get("city", "Unknown")
        geo["ip_country"] = ip_geo.get("country", "Unknown")
        geo["is_proxy"] = ip_geo.get("is_proxy", False)
        geo["is_hosting"] = ip_geo.get("is_hosting", False)
    else:
        geo = await _get_geolocation(ip)
        geo["source"] = "ip_lookup"
    
    # Record velocity for fraud detection
    store.record_velocity(req.device_fingerprint)
    
    # Update in-memory
    metadata = {
        "device_fingerprint": req.device_fingerprint,
        "ip_address": ip,
        "geolocation": geo,
        "user_agent": req.user_agent,
        "screen_resolution": req.screen_resolution,
        "timezone": req.timezone,
        "language": req.language,
        "platform": req.platform,
        "webrtc_supported": req.webrtc_supported,
        "canvas_hash": req.canvas_hash,
        "status": "active",
    }
    store.update(session_id, metadata)
    
    # Persist to SQLite
    db = await get_db()
    try:
        await db.execute(
            """UPDATE sessions SET device_fingerprint = ?, ip_address = ?,
               geolocation = ?, user_agent = ?, status = 'active', updated_at = datetime('now')
               WHERE id = ?""",
            (req.device_fingerprint, ip, json.dumps(geo), req.user_agent, session_id),
        )
        await db.commit()
    finally:
        await db.close()
    
    # Audit event
    await audit.emit(session_id, "METADATA_CAPTURED", "SESSION_INIT", {
        "ip": ip,
        "geolocation": geo,
        "device_fingerprint": req.device_fingerprint[:16] + "...",
        "platform": req.platform,
        "canvas_hash": req.canvas_hash,
    })
    
    return {"status": "ok", "ip": ip, "geolocation": geo}


@router.post("/{session_id}/heartbeat")
async def heartbeat(session_id: str):
    """Renew session heartbeat. Called every 30s by frontend."""
    session = store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    store.update(session_id, {"last_heartbeat": datetime.utcnow().isoformat()})
    return {"status": "alive", "session_id": session_id}


@router.post("/{session_id}/end")
async def end_session(session_id: str):
    """End a session."""
    session = store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    store.update(session_id, {"status": "completed"})
    
    db = await get_db()
    try:
        await db.execute(
            "UPDATE sessions SET status = 'completed', updated_at = datetime('now') WHERE id = ?",
            (session_id,),
        )
        await db.commit()
    finally:
        await db.close()
    
    await audit.emit(session_id, "SESSION_ENDED", "SESSION_COMPLETE", {})
    
    return {"status": "completed", "session_id": session_id}


@router.delete("/{session_id}")
async def delete_session(session_id: str, token: str):
    """Terminate and delete a session. Requires valid token."""
    payload = _validate_token(token)
    if payload["session_id"] != session_id:
        raise HTTPException(status_code=403, detail="Token does not match session")
    
    store.delete(session_id)
    
    db = await get_db()
    try:
        await db.execute(
            "UPDATE sessions SET status = 'terminated', updated_at = datetime('now') WHERE id = ?",
            (session_id,),
        )
        await db.commit()
    finally:
        await db.close()
    
    await audit.emit(session_id, "SESSION_TERMINATED", "SESSION_INIT", {})
    
    return {"terminated": True, "session_id": session_id}


@router.get("")
async def list_sessions():
    """List all sessions (for dashboard)."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM sessions ORDER BY created_at DESC LIMIT 100"
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        await db.close()
