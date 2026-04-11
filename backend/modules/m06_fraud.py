"""
M06 — Fraud Signal Detection Engine
Multi-signal algorithmic fraud scoring (NOT just LLM-based).
5 independent signals → composite score 0-100.
"""

import json
import os
import hashlib
from datetime import datetime
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import httpx

from config import settings
from database import get_db
from session_store import store
from events import audit

router = APIRouter(prefix="/api/fraud", tags=["M06 - Fraud"])


# ──────────────────────────────────────────────────────────────────
# Signal Weights
# ──────────────────────────────────────────────────────────────────

SIGNAL_WEIGHTS = {
    "geo_mismatch": 0.20,        # IP location vs stated city
    "device_anomaly": 0.20,      # Emulator/VPN/headless detection
    "age_inconsistency": 0.15,   # Vision vs declared age
    "transcript_contradiction": 0.25,  # LLM-flagged inconsistencies
    "velocity_check": 0.20,      # Same device/IP in time window
}


HTTP_TIMEOUT_SECONDS = 6.0
MAX_DEVICE_API_ERRORS = 2


def _resolve_client_ip(session: dict) -> str:
    """Best-effort client IP extraction from session."""
    ip = (session.get("ip_address") or "").strip()
    if not ip:
        return "unknown"
    if "," in ip:
        ip = ip.split(",")[0].strip()
    return ip


def _safe_hash(value: str) -> str:
    """Hash raw identifiers before sending to external verifiers."""
    if not value:
        return ""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


async def _call_json_api(
    method: str,
    url: str,
    *,
    params: Optional[dict] = None,
    json_payload: Optional[dict] = None,
    headers: Optional[dict] = None,
) -> dict:
    """HTTP helper with strict timeout and empty dict fallback."""
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as client:
            resp = await client.request(method, url, params=params, json=json_payload, headers=headers)
        if resp.status_code >= 400:
            return {}
        return resp.json() if resp.content else {}
    except Exception:
        return {}


async def _verify_geolocation(ip: str, fallback_geo: dict) -> dict:
    """
    Verify geolocation with primary API.
    Primary source defaults to settings.GEOIP_API_URL (same contract as ip-api).
    """
    if ip in ("unknown", "", "127.0.0.1", "::1", "localhost"):
        return {"verified": False, "source": "local", "data": fallback_geo or {}}

    geo_url = os.getenv("FRAUD_GEO_VERIFY_URL", settings.GEOIP_API_URL).rstrip("/")
    data = await _call_json_api("GET", f"{geo_url}/{ip}")

    if not data:
        return {"verified": False, "source": "geo_fallback", "data": fallback_geo or {}}

    normalized = {
        "city": data.get("city") or data.get("regionName") or "Unknown",
        "region": data.get("regionName", "Unknown"),
        "country": data.get("country", "Unknown"),
        "lat": data.get("lat", 0),
        "lon": data.get("lon", 0),
        "isp": data.get("isp", "Unknown"),
        "is_proxy": data.get("proxy", False),
        "is_hosting": data.get("hosting", False),
    }
    return {"verified": True, "source": "geo_api", "data": normalized}


async def _verify_vpn_proxy(ip: str, geo_data: dict) -> dict:
    """
    VPN/proxy verification.
    Uses IPQualityScore when key exists, else falls back to geolocation proxy flags.
    """
    if ip in ("unknown", "", "127.0.0.1", "::1", "localhost"):
        return {"verified": False, "source": "local", "is_vpn": False, "is_proxy": False, "risk_score": 0}

    key = os.getenv("IPQUALITYSCORE_API_KEY", "").strip()
    if key:
        # Example: https://www.ipqualityscore.com/documentation/proxy-detection-api/overview
        base_url = os.getenv("IPQS_API_URL", "https://ipqualityscore.com/api/json/ip").rstrip("/")
        data = await _call_json_api("GET", f"{base_url}/{key}/{ip}")
        if data:
            return {
                "verified": True,
                "source": "ipqualityscore",
                "is_vpn": bool(data.get("vpn", False)),
                "is_proxy": bool(data.get("proxy", False)),
                "is_tor": bool(data.get("tor", False)),
                "risk_score": int(data.get("fraud_score", 0) or 0),
                "raw": data,
            }

    # Fallback from geolocation flags when external VPN API unavailable.
    return {
        "verified": False,
        "source": "geo_flags",
        "is_vpn": bool(geo_data.get("is_proxy", False)),
        "is_proxy": bool(geo_data.get("is_proxy", False)),
        "is_tor": False,
        "risk_score": 30 if geo_data.get("is_proxy", False) else 0,
    }


async def _verify_device(session: dict, ip: str) -> dict:
    """
    Device verification via optional external API.
    If no external endpoint configured, executes deterministic local checks.
    """
    fp = session.get("device_fingerprint", "") or ""
    ua = (session.get("user_agent", "") or "").lower()
    platform = (session.get("platform", "") or "").lower()
    webrtc_supported = session.get("webrtc_supported")

    device_api_url = os.getenv("FRAUD_DEVICE_VERIFY_API_URL", "").strip()
    device_api_key = os.getenv("FRAUD_DEVICE_VERIFY_API_KEY", "").strip()

    local_flags = {
        "headless": any(s in ua for s in ["headless", "phantomjs", "selenium", "puppeteer", "playwright"]),
        "automation": any(s in ua for s in ["bot", "crawler", "spider", "python-requests", "curl", "wget"]),
        "emulator": any(s in ua for s in ["android sdk", "genymotion", "bluestacks", "nox", "memu"]),
        "short_fp": bool(fp and len(fp) < 8),
        "webrtc_disabled": webrtc_supported is False,
    }
    local_risk = 0
    if local_flags["emulator"]:
        local_risk += 30
    if local_flags["headless"]:
        local_risk += 35
    if local_flags["automation"]:
        local_risk += 40
    if local_flags["short_fp"]:
        local_risk += 15
    if local_flags["webrtc_disabled"]:
        local_risk += 10
    local_risk = min(local_risk, 100)

    if not device_api_url:
        return {
            "verified": False,
            "source": "local_heuristics",
            "risk_score": local_risk,
            "device_trust": max(0, 100 - local_risk),
            "flags": local_flags,
            "platform": platform,
        }

    headers = {"Content-Type": "application/json"}
    if device_api_key:
        headers["Authorization"] = f"Bearer {device_api_key}"

    payload = {
        "fingerprint_hash": _safe_hash(fp),
        "user_agent": ua[:512],
        "ip": ip,
        "platform": platform,
        "webrtc_supported": webrtc_supported,
    }
    data = await _call_json_api("POST", device_api_url, json_payload=payload, headers=headers)
    if not data:
        return {
            "verified": False,
            "source": "local_heuristics",
            "risk_score": local_risk,
            "device_trust": max(0, 100 - local_risk),
            "flags": local_flags,
            "platform": platform,
        }

    return {
        "verified": True,
        "source": "device_api",
        "risk_score": int(data.get("risk_score", local_risk)),
        "device_trust": int(data.get("device_trust", max(0, 100 - local_risk))),
        "flags": data.get("flags", local_flags),
        "platform": platform,
        "raw": data,
    }


async def _run_external_verifications(session_id: str, session: dict) -> dict:
    """Run all verification methods and store snapshot into session."""
    ip = _resolve_client_ip(session)
    fallback_geo = session.get("geolocation", {}) if isinstance(session.get("geolocation"), dict) else {}

    geo_verification = await _verify_geolocation(ip, fallback_geo)
    geo_data = geo_verification.get("data", fallback_geo)
    vpn_verification = await _verify_vpn_proxy(ip, geo_data if isinstance(geo_data, dict) else {})
    device_verification = await _verify_device(session, ip)

    result = {
        "ip": ip,
        "checked_at": datetime.utcnow().isoformat(),
        "geolocation": geo_verification,
        "vpn_proxy": vpn_verification,
        "device": device_verification,
    }
    store.update(session_id, {"fraud_verification": result, "geolocation": geo_data})
    return result


def _score_geo_mismatch(session: dict) -> dict:
    """Signal 1: IP geolocation vs stated city — 0-100."""
    verification = session.get("fraud_verification", {})
    verified_geo = (verification.get("geolocation", {}) or {}).get("data", {}) if isinstance(verification, dict) else {}
    geo = verified_geo if isinstance(verified_geo, dict) and verified_geo else session.get("geolocation", {})
    fields = session.get("extracted_fields", {})
    
    stated_city = None
    if isinstance(fields.get("city"), dict):
        stated_city = fields["city"].get("value", "").lower()
    elif isinstance(fields.get("city"), str):
        stated_city = fields["city"].lower()
    
    ip_city = geo.get("city", "").lower() if isinstance(geo, dict) else ""
    
    # Edge cases
    if not stated_city or not ip_city or ip_city == "local":
        return {"score": 0, "detail": "Insufficient data for geo comparison", "raw": {"stated": stated_city, "ip": ip_city}}
    
    if stated_city == ip_city or stated_city in ip_city or ip_city in stated_city:
        return {"score": 0, "detail": "Cities match", "raw": {"stated": stated_city, "ip": ip_city}}
    
    # Check for proxy/hosting
    is_proxy = geo.get("is_proxy", False) if isinstance(geo, dict) else False
    is_hosting = geo.get("is_hosting", False) if isinstance(geo, dict) else False
    vpn_data = (verification.get("vpn_proxy", {}) if isinstance(verification, dict) else {}) or {}
    vpn_detected = bool(vpn_data.get("is_vpn", False))

    score = 50  # Cities don't match
    if is_proxy or vpn_detected:
        score += 30
    if is_hosting:
        score += 20
    
    return {
        "score": min(score, 100),
        "detail": f"City mismatch: stated='{stated_city}', IP='{ip_city}'" +
                  (", VPN/proxy detected" if (is_proxy or vpn_detected) else "") +
                  (", hosting provider" if is_hosting else ""),
        "raw": {"stated": stated_city, "ip": ip_city, "is_proxy": is_proxy, "is_hosting": is_hosting, "vpn_detected": vpn_detected},
    }


def _score_device_anomaly(session: dict) -> dict:
    """Signal 2: Device anomaly detection — 0-100."""
    ua = session.get("user_agent", "").lower()
    fp = session.get("device_fingerprint", "")
    platform = session.get("platform", "").lower()
    
    score = 0
    details = []
    
    # Emulator detection
    emulator_signs = ["android sdk", "genymotion", "bluestacks", "nox", "memu"]
    for sign in emulator_signs:
        if sign in ua:
            score += 40
            details.append(f"Emulator detected: {sign}")
            break
    
    # Headless browser detection
    headless_signs = ["headless", "phantomjs", "selenium", "puppeteer", "playwright"]
    for sign in headless_signs:
        if sign in ua:
            score += 50
            details.append(f"Headless browser: {sign}")
            break
    
    # Bot detection
    bot_signs = ["bot", "crawler", "spider", "curl", "wget", "python-requests"]
    for sign in bot_signs:
        if sign in ua:
            score += 60
            details.append(f"Bot/automated: {sign}")
            break
    
    # Very short fingerprint (potentially spoofed)
    if fp and len(fp) < 8:
        score += 20
        details.append("Suspiciously short device fingerprint")
    
    # Missing WebRTC (potential automation)
    if session.get("webrtc_supported") is False:
        score += 15
        details.append("WebRTC not supported (unusual)")
    
    verification = session.get("fraud_verification", {})
    device_verification = (verification.get("device", {}) if isinstance(verification, dict) else {}) or {}
    vpn_verification = (verification.get("vpn_proxy", {}) if isinstance(verification, dict) else {}) or {}

    device_risk = int(device_verification.get("risk_score", 0) or 0)
    if device_risk > 0:
        # External/local verifier contributes as confidence-boosted risk.
        boost = min(int(device_risk * 0.4), 40)
        score += boost
        details.append(f"Device verifier risk: {device_risk} (+{boost})")

    vpn_risk = int(vpn_verification.get("risk_score", 0) or 0)
    if vpn_risk >= 70:
        score += 20
        details.append("High VPN/proxy risk from IP verifier")

    if not details:
        details.append("No device anomalies detected")
    
    return {"score": min(score, 100), "detail": "; ".join(details), "raw": {"user_agent": ua[:100], "platform": platform}}


def _score_age_inconsistency(session: dict) -> dict:
    """Signal 3: Vision-estimated age vs declared age — 0-100."""
    vision_results = session.get("vision_results", [])
    fields = session.get("extracted_fields", {})
    
    declared_age = None
    if isinstance(fields.get("age"), dict):
        try:
            declared_age = int(fields["age"].get("value", 0))
        except (ValueError, TypeError):
            declared_age = None
    elif isinstance(fields.get("age"), (int, float)):
        declared_age = int(fields["age"])
    
    if not vision_results or declared_age is None:
        return {"score": 0, "detail": "Insufficient data for age comparison", "raw": {}}
    
    # Average estimated age from vision
    ages = [r.get("estimated_age") for r in vision_results if r.get("estimated_age") is not None]
    if not ages:
        return {"score": 0, "detail": "No age estimates from vision", "raw": {}}
    
    avg_age = sum(ages) / len(ages)
    delta = abs(avg_age - declared_age)
    
    if delta <= 3:
        score = 0
    elif delta <= settings.AGE_DELTA_THRESHOLD:
        score = int((delta / settings.AGE_DELTA_THRESHOLD) * 50)
    else:
        score = min(50 + int((delta - settings.AGE_DELTA_THRESHOLD) * 5), 100)
    
    return {
        "score": score,
        "detail": f"Declared age: {declared_age}, Estimated: {avg_age:.1f}, Delta: {delta:.1f}",
        "raw": {"declared": declared_age, "estimated": round(avg_age, 1), "delta": round(delta, 1)},
    }


def _score_transcript_contradictions(session: dict) -> dict:
    """Signal 4: LLM-detected contradictions in transcript — 0-100."""
    assessment = session.get("llm_assessment", {})
    contradictions = assessment.get("contradictions", [])
    
    if not contradictions:
        return {"score": 0, "detail": "No contradictions detected", "raw": {}}
    
    # Score based on number and severity
    score = 0
    for c in contradictions:
        severity = c.get("severity", "low")
        if severity == "high":
            score += 35
        elif severity == "medium":
            score += 20
        else:
            score += 10
    
    return {
        "score": min(score, 100),
        "detail": f"{len(contradictions)} contradiction(s) found",
        "raw": {"contradictions": contradictions},
    }


def _score_velocity(session: dict) -> dict:
    """Signal 5: Velocity check — same device applying multiple times — 0-100."""
    fp = session.get("device_fingerprint", "")
    if not fp:
        return {"score": 0, "detail": "No fingerprint for velocity check", "raw": {}}
    
    count = store.get_velocity_count(fp, settings.VELOCITY_WINDOW_MINUTES)
    
    if count <= 1:
        score = 0
        detail = "First session from this device"
    elif count <= settings.MAX_SESSIONS_PER_DEVICE:
        score = int((count / settings.MAX_SESSIONS_PER_DEVICE) * 40)
        detail = f"{count} sessions from same device within {settings.VELOCITY_WINDOW_MINUTES}min"
    else:
        score = min(40 + (count - settings.MAX_SESSIONS_PER_DEVICE) * 20, 100)
        detail = f"HIGH: {count} sessions from same device (limit: {settings.MAX_SESSIONS_PER_DEVICE})"
    
    return {"score": score, "detail": detail, "raw": {"session_count": count, "window_minutes": settings.VELOCITY_WINDOW_MINUTES}}


# ──────────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────────

@router.post("/{session_id}/score")
async def compute_fraud_score(session_id: str):
    """
    Compute composite fraud score from 5 algorithmic signals.
    Score 0-100: 0-30=Low, 31-60=Medium, 61-100=High.
    """
    session = store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Fresh external verification snapshot before scoring.
    verification = await _run_external_verifications(session_id, session)
    session = store.get(session_id) or session
    
    # Compute each signal
    signals = {
        "geo_mismatch": _score_geo_mismatch(session),
        "device_anomaly": _score_device_anomaly(session),
        "age_inconsistency": _score_age_inconsistency(session),
        "transcript_contradiction": _score_transcript_contradictions(session),
        "velocity_check": _score_velocity(session),
    }
    
    # Weighted composite
    composite = sum(
        signals[name]["score"] * SIGNAL_WEIGHTS[name]
        for name in SIGNAL_WEIGHTS
    )
    composite = round(min(composite, 100), 2)
    
    # Risk level
    if composite <= settings.FRAUD_MEDIUM_THRESHOLD:
        risk_level = "low"
    elif composite <= settings.FRAUD_HIGH_THRESHOLD:
        risk_level = "medium"
    else:
        risk_level = "high"
    
    result = {
        "session_id": session_id,
        "composite_score": composite,
        "risk_level": risk_level,
        "signals": signals,
        "verification": verification,
        "weights": SIGNAL_WEIGHTS,
        "timestamp": datetime.utcnow().isoformat(),
    }
    
    # Store
    store.update(session_id, {"fraud_score": result})
    
    # Persist
    try:
        db = await get_db()
        try:
            await db.execute(
                """INSERT INTO fraud_scores 
                   (session_id, composite_score, geo_mismatch_score, device_anomaly_score,
                    age_inconsistency_score, transcript_contradiction_score, velocity_score,
                    signal_breakdown, risk_level)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    session_id,
                    composite,
                    signals["geo_mismatch"]["score"],
                    signals["device_anomaly"]["score"],
                    signals["age_inconsistency"]["score"],
                    signals["transcript_contradiction"]["score"],
                    signals["velocity_check"]["score"],
                    json.dumps(signals),
                    risk_level,
                ),
            )
            await db.commit()
        finally:
            await db.close()
    except Exception:
        pass
    
    await audit.emit(session_id, "FRAUD_SCORED", "FRAUD", {
        "composite_score": composite,
        "risk_level": risk_level,
        "signal_scores": {k: v["score"] for k, v in signals.items()},
    })
    
    return result


@router.post("/{session_id}/verify")
async def verify_fraud_signals(session_id: str):
    """
    Run standalone verification methods for:
    - geolocation (IP → city/region/country)
    - VPN/proxy detection
    - device verification
    """
    session = store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    result = await _run_external_verifications(session_id, session)
    await audit.emit(session_id, "FRAUD_VERIFICATION_RUN", "FRAUD", {
        "ip": result.get("ip"),
        "geo_source": (result.get("geolocation") or {}).get("source"),
        "vpn_source": (result.get("vpn_proxy") or {}).get("source"),
        "device_source": (result.get("device") or {}).get("source"),
    })
    return result


@router.get("/{session_id}")
async def get_fraud_report(session_id: str):
    """Get full fraud report for a session."""
    session = store.get(session_id)
    if session and session.get("fraud_score"):
        return session["fraud_score"]
    
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM fraud_scores WHERE session_id = ? ORDER BY created_at DESC LIMIT 1",
            (session_id,),
        )
        row = await cursor.fetchone()
        if row:
            data = dict(row)
            data["signal_breakdown"] = json.loads(data.get("signal_breakdown", "{}"))
            return data
    finally:
        await db.close()
    
    raise HTTPException(status_code=404, detail="No fraud report found")
