"""
AgentFinance AI — SQLite Database Layer
All tables for the 10-tier pipeline.
"""

import aiosqlite
import os
from pathlib import Path
from config import settings

DB_PATH = settings.DATABASE_PATH

# ──────────────────────────────────────────────────────────────────
# Schema DDL
# ──────────────────────────────────────────────────────────────────

SCHEMA_SQL = """
-- M01: Sessions
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    token TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'created',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    device_fingerprint TEXT,
    ip_address TEXT,
    geolocation TEXT,
    user_agent TEXT,
    applicant_name TEXT,
    applicant_id TEXT
);

-- M01: Session metadata
CREATE TABLE IF NOT EXISTS session_metadata (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- M02: Transcripts
CREATE TABLE IF NOT EXISTS transcripts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    segment_index INTEGER NOT NULL,
    text TEXT NOT NULL,
    start_time REAL,
    end_time REAL,
    confidence REAL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- M02: Extracted fields
CREATE TABLE IF NOT EXISTS extracted_fields (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    field_name TEXT NOT NULL,
    field_value TEXT,
    confidence REAL NOT NULL DEFAULT 0.0,
    source TEXT DEFAULT 'stt',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- M03: Consent records
CREATE TABLE IF NOT EXISTS consent_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    consent_type TEXT NOT NULL DEFAULT 'verbal',
    phrase_detected TEXT NOT NULL,
    transcript_segment TEXT NOT NULL,
    segment_hash TEXT NOT NULL,
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    is_consent INTEGER NOT NULL DEFAULT 1
);

-- M04: Vision results
CREATE TABLE IF NOT EXISTS vision_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    frame_index INTEGER NOT NULL,
    is_live INTEGER NOT NULL DEFAULT 0,
    liveness_score REAL NOT NULL DEFAULT 0.0,
    estimated_age REAL,
    face_detected INTEGER NOT NULL DEFAULT 0,
    blink_detected INTEGER NOT NULL DEFAULT 0,
    head_pose TEXT,
    texture_score REAL,
    model_used TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- M05: LLM assessments  
CREATE TABLE IF NOT EXISTS llm_assessments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    intent_category TEXT,
    intent_confidence REAL,
    risk_persona TEXT,
    risk_confidence REAL,
    reasoning_trace TEXT,
    contradictions TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- M06: Fraud scores
CREATE TABLE IF NOT EXISTS fraud_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    composite_score REAL NOT NULL DEFAULT 0.0,
    geo_mismatch_score REAL DEFAULT 0.0,
    device_anomaly_score REAL DEFAULT 0.0,
    age_inconsistency_score REAL DEFAULT 0.0,
    transcript_contradiction_score REAL DEFAULT 0.0,
    velocity_score REAL DEFAULT 0.0,
    signal_breakdown TEXT,
    risk_level TEXT DEFAULT 'low',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- M07: Bureau results
CREATE TABLE IF NOT EXISTS bureau_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    applicant_id TEXT,
    credit_score INTEGER,
    active_loans INTEGER DEFAULT 0,
    dpd_history TEXT,
    written_off INTEGER DEFAULT 0,
    policy_decision TEXT,
    policy_explanation TEXT,
    rule_evaluations TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- M08: Offers
CREATE TABLE IF NOT EXISTS offers (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    eligible_amount REAL,
    interest_rate REAL,
    tenure_months INTEGER,
    emi_amount REAL,
    emi_table TEXT,
    status TEXT NOT NULL DEFAULT 'generated',
    negotiation_rounds INTEGER DEFAULT 0,
    negotiation_log TEXT,
    accepted_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- M09: Audit events
CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    event_type TEXT NOT NULL,
    stage TEXT NOT NULL,
    data TEXT,
    timestamp TEXT NOT NULL DEFAULT (datetime('now'))
);

-- M09: Pipeline state
CREATE TABLE IF NOT EXISTS pipeline_states (
    session_id TEXT PRIMARY KEY REFERENCES sessions(id),
    current_stage TEXT NOT NULL DEFAULT 'SESSION_INIT',
    stages_completed TEXT DEFAULT '[]',
    stages_failed TEXT DEFAULT '[]',
    failure_mode TEXT,
    recovery_action TEXT,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_transcripts_session ON transcripts(session_id);
CREATE INDEX IF NOT EXISTS idx_extracted_fields_session ON extracted_fields(session_id);
CREATE INDEX IF NOT EXISTS idx_consent_session ON consent_records(session_id);
CREATE INDEX IF NOT EXISTS idx_vision_session ON vision_results(session_id);
CREATE INDEX IF NOT EXISTS idx_audit_session ON audit_events(session_id);
CREATE INDEX IF NOT EXISTS idx_audit_type ON audit_events(event_type);
CREATE INDEX IF NOT EXISTS idx_offers_session ON offers(session_id);
""" 


async def get_db() -> aiosqlite.Connection:
    """Get a database connection. Creates the DB file + tables if needed."""
    db_path = Path(DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    db = await aiosqlite.connect(str(db_path))
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    return db


async def init_db():
    """Initialize database with schema."""
    db = await get_db()
    try:
        await db.executescript(SCHEMA_SQL)
        await db.commit()
        print("[OK] Database initialized successfully")
    finally:
        await db.close()
