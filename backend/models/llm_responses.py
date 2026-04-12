"""
Pydantic schemas for LLM JSON outputs.

Used to validate and coerce the raw JSON returned by Groq so that downstream
modules always receive well-typed data — even when the LLM returns missing keys,
wrong types, or extra fields.

Each schema has:
  * Strict field declarations with sensible defaults
  * A class-method `from_raw(raw: str | dict)` that:
      1. JSON-parses if necessary
      2. Strips markdown code fences
      3. Validates and coerces via Pydantic
      4. Raises `ValidationError` on unrecoverable failures
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator, ValidationError


# ─────────────────────────────────────────────────────────────────
# Shared helpers
# ─────────────────────────────────────────────────────────────────

def _clean_raw(raw: str) -> str:
    """Strip markdown code fences and leading/trailing whitespace."""
    raw = raw.strip()
    if raw.startswith("```"):
        # Strip opening fence (e.g. ```json)
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        # Strip closing fence
        raw = raw.rsplit("```", 1)[0]
    return raw.strip()


def _parse_json_permissive(raw: str) -> dict:
    """
    Parse JSON from `raw`, trying multiple recovery strategies:
      1. Direct parse
      2. Find the largest {...} block
      3. Strip trailing commas before } or ]
    Raises ValueError if all strategies fail.
    """
    text = _clean_raw(raw)

    # Strategy 1: direct
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Strategy 2: find outermost { ... }
    start = text.find("{")
    if start != -1:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
            if depth == 0:
                candidate = text[start: i + 1]
                # Strategy 3: remove trailing commas before } or ]
                candidate = re.sub(r",\s*([}\]])", r"\1", candidate)
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    break

    raise ValueError(f"Cannot parse JSON from LLM output: {raw[:200]!r}")


# ─────────────────────────────────────────────────────────────────
# 1. Field extraction (M02 STT)
# ─────────────────────────────────────────────────────────────────

class FieldEntry(BaseModel):
    value: Optional[str] = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    @field_validator("confidence", mode="before")
    @classmethod
    def clamp_confidence(cls, v: Any) -> float:
        try:
            return max(0.0, min(1.0, float(v)))
        except (TypeError, ValueError):
            return 0.0


class ExtractionResponse(BaseModel):
    name: FieldEntry = Field(default_factory=FieldEntry)
    age: FieldEntry = Field(default_factory=FieldEntry)
    employment_type: FieldEntry = Field(default_factory=FieldEntry)
    monthly_income: FieldEntry = Field(default_factory=FieldEntry)
    loan_purpose: FieldEntry = Field(default_factory=FieldEntry)
    requested_amount: FieldEntry = Field(default_factory=FieldEntry)
    city: FieldEntry = Field(default_factory=FieldEntry)
    employer_name: FieldEntry = Field(default_factory=FieldEntry)

    model_config = {"extra": "ignore"}

    @classmethod
    def from_raw(cls, raw: str | dict) -> "ExtractionResponse":
        data = raw if isinstance(raw, dict) else _parse_json_permissive(raw)
        # Coerce plain string / number values to FieldEntry dicts
        normalized: dict[str, Any] = {}
        for k, v in data.items():
            if isinstance(v, dict):
                normalized[k] = v
            elif v is not None:
                normalized[k] = {"value": str(v), "confidence": 0.7}
            else:
                normalized[k] = {"value": None, "confidence": 0.0}
        return cls.model_validate(normalized)


# ─────────────────────────────────────────────────────────────────
# 2. LLM assessment (M05)
# ─────────────────────────────────────────────────────────────────

class Contradiction(BaseModel):
    field1: str = ""
    field2: str = ""
    description: str = ""
    severity: str = "low"

    model_config = {"extra": "ignore"}


_VALID_INTENTS = {
    "home_improvement", "medical_emergency", "education", "debt_consolidation",
    "vehicle_purchase", "business_expansion", "wedding", "travel",
    "consumer_electronics", "other",
}
_VALID_PERSONAS = {
    "conservative_borrower", "moderate_borrower", "aggressive_borrower",
    "first_time_borrower", "distressed_borrower",
}


class AssessmentResponse(BaseModel):
    intent_category: str = "other"
    intent_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    risk_persona: str = "moderate_borrower"
    risk_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    reasoning_trace: list[str] = Field(default_factory=list)
    contradictions: list[Contradiction] = Field(default_factory=list)
    tone_indicators: list[str] = Field(default_factory=list)
    distress_signals: bool = False
    summary: str = ""

    model_config = {"extra": "ignore"}

    @field_validator("intent_category", mode="before")
    @classmethod
    def validate_intent(cls, v: Any) -> str:
        return v if v in _VALID_INTENTS else "other"

    @field_validator("risk_persona", mode="before")
    @classmethod
    def validate_persona(cls, v: Any) -> str:
        return v if v in _VALID_PERSONAS else "moderate_borrower"

    @field_validator("intent_confidence", "risk_confidence", mode="before")
    @classmethod
    def clamp_conf(cls, v: Any) -> float:
        try:
            return max(0.0, min(1.0, float(v)))
        except (TypeError, ValueError):
            return 0.5

    @field_validator("reasoning_trace", mode="before")
    @classmethod
    def coerce_trace(cls, v: Any) -> list[str]:
        if isinstance(v, list):
            return [str(x) for x in v]
        if isinstance(v, str):
            return [v]
        return []

    @field_validator("contradictions", mode="before")
    @classmethod
    def coerce_contradictions(cls, v: Any) -> list[dict]:
        if isinstance(v, list):
            return v
        return []

    @classmethod
    def from_raw(cls, raw: str | dict) -> "AssessmentResponse":
        data = raw if isinstance(raw, dict) else _parse_json_permissive(raw)
        return cls.model_validate(data)


# ─────────────────────────────────────────────────────────────────
# 3. Negotiation response (M08)
# ─────────────────────────────────────────────────────────────────

class AdjustedOffer(BaseModel):
    amount: Optional[float] = None
    rate: Optional[float] = None
    tenure: Optional[int] = None
    emi: Optional[float] = None

    model_config = {"extra": "ignore"}

    @field_validator("amount", "rate", "emi", mode="before")
    @classmethod
    def coerce_float(cls, v: Any) -> Optional[float]:
        if v is None:
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    @field_validator("tenure", mode="before")
    @classmethod
    def coerce_int(cls, v: Any) -> Optional[int]:
        if v is None:
            return None
        try:
            return int(v)
        except (TypeError, ValueError):
            return None


class NegotiationResponse(BaseModel):
    response_text: str = "I understand. Let me review the terms once more."
    adjusted_offer: Optional[AdjustedOffer] = None
    is_final: bool = False

    model_config = {"extra": "ignore"}

    @field_validator("response_text", mode="before")
    @classmethod
    def coerce_text(cls, v: Any) -> str:
        return str(v) if v else "I understand. Let me review the terms once more."

    @classmethod
    def from_raw(cls, raw: str | dict) -> "NegotiationResponse":
        data = raw if isinstance(raw, dict) else _parse_json_permissive(raw)
        return cls.model_validate(data)
