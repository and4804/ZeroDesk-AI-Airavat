"""
AgentFinance AI — Audit Event System
All agent decisions and state transitions emit structured events.
Events are stored in SQLite and kept in-memory for quick access.
"""

import json
from datetime import datetime
from typing import Any, Optional
from database import get_db


class AuditEventEmitter:
    """Emits and stores structured audit events for every pipeline action."""
    
    def __init__(self):
        self._events: dict[str, list[dict]] = {}  # session_id -> [events]
    
    async def emit(
        self,
        session_id: str,
        event_type: str,
        stage: str,
        data: dict[str, Any] | None = None,
    ) -> dict:
        """
        Emit a structured audit event.
        
        Args:
            session_id: The session this event belongs to
            event_type: e.g. 'STAGE_TRANSITION', 'FIELD_EXTRACTED', 'CONSENT_DETECTED'
            stage: Pipeline stage e.g. 'STT', 'VISION', 'FRAUD'
            data: Arbitrary payload for the event
        
        Returns:
            The created event dict
        """
        event = {
            "session_id": session_id,
            "event_type": event_type,
            "stage": stage,
            "data": data or {},
            "timestamp": datetime.utcnow().isoformat(),
        }
        
        # In-memory store
        if session_id not in self._events:
            self._events[session_id] = []
        self._events[session_id].append(event)
        
        # Persist to SQLite
        try:
            db = await get_db()
            try:
                await db.execute(
                    """INSERT INTO audit_events (session_id, event_type, stage, data, timestamp)
                       VALUES (?, ?, ?, ?, ?)""",
                    (session_id, event_type, stage, json.dumps(data or {}), event["timestamp"]),
                )
                await db.commit()
            finally:
                await db.close()
        except Exception as e:
            print(f"[WARN] Failed to persist audit event: {e}")
        
        return event
    
    def get_events(self, session_id: str) -> list[dict]:
        """Get all events for a session from memory."""
        return self._events.get(session_id, [])
    
    def get_events_by_type(self, session_id: str, event_type: str) -> list[dict]:
        """Get events filtered by type."""
        return [
            e for e in self._events.get(session_id, [])
            if e["event_type"] == event_type
        ]
    
    async def get_events_from_db(self, session_id: str) -> list[dict]:
        """Get all events from database (for audit reports)."""
        db = await get_db()
        try:
            cursor = await db.execute(
                "SELECT * FROM audit_events WHERE session_id = ? ORDER BY timestamp",
                (session_id,),
            )
            rows = await cursor.fetchall()
            return [
                {
                    "id": row["id"],
                    "session_id": row["session_id"],
                    "event_type": row["event_type"],
                    "stage": row["stage"],
                    "data": json.loads(row["data"]) if row["data"] else {},
                    "timestamp": row["timestamp"],
                }
                for row in rows
            ]
        finally:
            await db.close()


# Singleton
audit = AuditEventEmitter()
