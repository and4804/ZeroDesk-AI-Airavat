"""
AgentFinance AI — In-Memory Session Store
Replaces Redis for hackathon simplicity. Stores transient session state.
"""

import time
from typing import Any, Optional
from datetime import datetime, timedelta
import threading


class SessionStore:
    """Thread-safe in-memory session state manager."""
    
    def __init__(self):
        self._sessions: dict[str, dict[str, Any]] = {}
        self._velocity: dict[str, list[float]] = {}  # fingerprint -> [timestamps]
        self._lock = threading.Lock()
    
    def create(self, session_id: str, data: dict[str, Any] | None = None) -> dict:
        """Create a new session."""
        with self._lock:
            session = {
                "id": session_id,
                "status": "created",
                "created_at": datetime.utcnow().isoformat(),
                "pipeline_stage": "SESSION_INIT",
                "stages_completed": [],
                "stages_failed": [],
                "transcript": [],
                "extracted_fields": {},
                "vision_results": [],
                "consent": None,
                "fraud_score": None,
                "bureau_result": None,
                "llm_assessment": None,
                "offer": None,
                "failure_mode": None,
                **(data or {}),
            }
            self._sessions[session_id] = session
            return session
    
    def get(self, session_id: str) -> Optional[dict]:
        """Get session by ID."""
        return self._sessions.get(session_id)
    
    def update(self, session_id: str, updates: dict[str, Any]) -> Optional[dict]:
        """Update session fields."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session:
                session.update(updates)
                session["updated_at"] = datetime.utcnow().isoformat()
            return session
    
    def delete(self, session_id: str) -> bool:
        """Delete a session."""
        with self._lock:
            return self._sessions.pop(session_id, None) is not None
    
    def list_all(self) -> list[dict]:
        """List all sessions."""
        return list(self._sessions.values())
    
    def append_transcript(self, session_id: str, segment: dict):
        """Append a transcript segment to session."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session:
                session["transcript"].append(segment)
    
    def get_full_transcript(self, session_id: str) -> str:
        """Get concatenated transcript text."""
        session = self._sessions.get(session_id)
        if not session:
            return ""
        return " ".join(seg.get("text", "") for seg in session.get("transcript", []))
    
    def append_vision(self, session_id: str, result: dict):
        """Append vision analysis result."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session:
                session["vision_results"].append(result)
    
    # --- Velocity tracking (for fraud detection) ---
    
    def record_velocity(self, fingerprint: str):
        """Record an access for velocity checking."""
        with self._lock:
            now = time.time()
            if fingerprint not in self._velocity:
                self._velocity[fingerprint] = []
            self._velocity[fingerprint].append(now)
    
    def get_velocity_count(self, fingerprint: str, window_minutes: int = 60) -> int:
        """Count accesses within time window."""
        with self._lock:
            now = time.time()
            cutoff = now - (window_minutes * 60)
            timestamps = self._velocity.get(fingerprint, [])
            # Clean old entries
            valid = [t for t in timestamps if t > cutoff]
            self._velocity[fingerprint] = valid
            return len(valid)


# Singleton instance
store = SessionStore()
