"""
M07 Configuration — Settings & cross-module default values.

Cross-module inputs (fraud_score, liveness_avg, consent_detected) have
assumed defaults so the bureau mock can run in complete isolation without
M03 / M04 / M06.  Override via query params at request time or by
changing the defaults here.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
SEED_DATA_PATH = DATA_DIR / "bureau_seed.json"
RULES_CONFIG_PATH = DATA_DIR / "rules_config.json"

# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------
PORT: int = int(os.getenv("BUREAU_MOCK_PORT", "8001"))
HOST: str = os.getenv("BUREAU_MOCK_HOST", "0.0.0.0")

# ---------------------------------------------------------------------------
# Score weights  (user-specified 35 / 25 / 20 / 20)
# ---------------------------------------------------------------------------
SCORE_WEIGHTS: dict[str, float] = {
    "payment_history": 0.35,
    "utilization": 0.25,
    "mix_age": 0.20,
    "new_credit": 0.20,
}

# ---------------------------------------------------------------------------
# Assumed defaults for cross-module signals
# When M07 runs standalone these values are used unless overridden via
# query parameters on the bureau endpoint.
# ---------------------------------------------------------------------------
DEFAULT_FRAUD_SCORE: int = 20          # M06 fraud_score (0-100, low = safe)
DEFAULT_LIVENESS_AVG: float = 0.85     # M04 liveness average (0-1, high = live)
DEFAULT_CONSENT_DETECTED: bool = True  # M03 consent flag

# Per-persona overrides (known demo applicant_ids)
PERSONA_OVERRIDES: dict[str, dict[str, Any]] = {
    "PRIYA-001":  {"fraud_score": 12,  "liveness_avg": 0.92, "consent_detected": True},
    "ROHIT-002":  {"fraud_score": 82,  "liveness_avg": 0.45, "consent_detected": True},
    "MEERA-003":  {"fraud_score": 35,  "liveness_avg": 0.88, "consent_detected": True},
}

# ---------------------------------------------------------------------------
# DPD "last 12 months" cutoff year — current year for filtering dpd_history
# ---------------------------------------------------------------------------
CURRENT_YEAR: int = 2026

# ---------------------------------------------------------------------------
# Helpers — loaded lazily at startup via lifespan
# ---------------------------------------------------------------------------
_seed_data: list[dict] | None = None
_rules_config: list[dict] | None = None


def load_seed_data() -> list[dict]:
    """Load and cache bureau_seed.json."""
    global _seed_data
    if _seed_data is None:
        with open(SEED_DATA_PATH, "r", encoding="utf-8") as f:
            _seed_data = json.load(f)
    return _seed_data


def load_rules_config() -> list[dict]:
    """Load and cache rules_config.json."""
    global _rules_config
    if _rules_config is None:
        with open(RULES_CONFIG_PATH, "r", encoding="utf-8") as f:
            _rules_config = json.load(f)
    return _rules_config


def get_seed_profile(applicant_id: str) -> dict | None:
    """Look up a seed profile by applicant_id (case-insensitive)."""
    for profile in load_seed_data():
        if profile["applicant_id"].upper() == applicant_id.upper():
            return profile
    return None
