"""
M07 Standalone Mocks — deterministic mock values for cross-module signals.

These allow M07 to be tested in complete isolation without M03 / M04 / M06.
Known demo persona IDs return preset values; unknown IDs get a
deterministic hash-based value so results are reproducible.
"""

from __future__ import annotations

import hashlib

from app.config import (
    DEFAULT_CONSENT_DETECTED,
    DEFAULT_FRAUD_SCORE,
    DEFAULT_LIVENESS_AVG,
    PERSONA_OVERRIDES,
)


def _deterministic_float(applicant_id: str, salt: str, lo: float, hi: float) -> float:
    """Hash-based float in [lo, hi], deterministic for a given ID + salt."""
    digest = hashlib.sha256(f"{applicant_id}:{salt}".encode()).hexdigest()
    # Use first 8 hex chars → 0..0xFFFFFFFF → normalise to [0,1]
    normalised = int(digest[:8], 16) / 0xFFFFFFFF
    return round(lo + normalised * (hi - lo), 4)


def _deterministic_int(applicant_id: str, salt: str, lo: int, hi: int) -> int:
    """Hash-based int in [lo, hi], deterministic for a given ID + salt."""
    return int(_deterministic_float(applicant_id, salt, float(lo), float(hi)))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_fraud_score(applicant_id: str) -> int:
    """
    Return a mock fraud score (0–100).

    For known demo personas, returns preset values from config.
    For unknown IDs, returns a deterministic hash-based value.
    """
    overrides = PERSONA_OVERRIDES.get(applicant_id.upper(), None)
    if overrides and "fraud_score" in overrides:
        return overrides["fraud_score"]
    return max(0, min(100, _deterministic_int(applicant_id, "fraud", 5, 50)))


def get_liveness_avg(applicant_id: str) -> float:
    """
    Return a mock liveness average (0.0–1.0).

    For known demo personas, returns preset values from config.
    For unknown IDs, returns a deterministic hash-based value.
    """
    overrides = PERSONA_OVERRIDES.get(applicant_id.upper(), None)
    if overrides and "liveness_avg" in overrides:
        return overrides["liveness_avg"]
    return max(0.0, min(1.0, _deterministic_float(applicant_id, "liveness", 0.6, 0.98)))


def get_consent_detected(applicant_id: str) -> bool:
    """
    Return a mock consent detection flag.

    For known demo personas, returns preset values from config.
    For unknown IDs, returns the global default (True).
    """
    overrides = PERSONA_OVERRIDES.get(applicant_id.upper(), None)
    if overrides and "consent_detected" in overrides:
        return overrides["consent_detected"]
    return DEFAULT_CONSENT_DETECTED
