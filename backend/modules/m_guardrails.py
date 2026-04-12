"""
M-Guardrails — Topic Relevance Guardrails for Loan Interview
Ensures the applicant stays on-topic during the STT interview.

Strategy (two-tier, no heavy models needed at import time):
  Tier 1 (fast): keyword membership — O(n) set intersection
  Tier 2 (semantic): cosine similarity against a fixed loan-intent TF-IDF
                     vector computed at module load time (pure numpy, no torch)

If the segment passes neither tier, the caller should redirect the user
back to the missing field instead of continuing extraction.
"""

from __future__ import annotations

import math
import re
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/guardrails", tags=["Guardrails"])

# ─────────────────────────────────────────────────────────────────
# Loan-domain keyword set  (case-insensitive)
# ─────────────────────────────────────────────────────────────────
LOAN_KEYWORDS: frozenset[str] = frozenset({
    # Identity / personal
    "name", "age", "old", "born", "gender",
    # Employment
    "employed", "employment", "salaried", "salary", "job", "work",
    "business", "self-employed", "freelance", "profession", "company",
    "employer", "designation", "office",
    # Income
    "income", "earn", "earning", "monthly", "annual", "yearly",
    "rupees", "rs", "inr", "lakh", "thousand", "crore", "k",
    "ctc", "package", "pay",
    # Loan specifics
    "loan", "emi", "amount", "interest", "rate", "tenure",
    "repay", "borrow", "credit", "bank", "finance",
    "principal", "installment",
    # Purpose
    "home", "house", "car", "vehicle", "education", "medical",
    "wedding", "travel", "renovation", "improvement", "business",
    "purpose", "reason", "need",
    # Consent
    "agree", "consent", "accept", "authorize", "yes", "proceed",
    # Location (for geo-fraud signals)
    "city", "live", "reside", "address", "state", "location",
})

# ─────────────────────────────────────────────────────────────────
# Canonical loan-intent sentences (for TF-IDF bag-of-words similarity)
# ─────────────────────────────────────────────────────────────────
_LOAN_SENTENCES = [
    "my name is and i want to apply for a home loan",
    "my monthly salary is rupees i am salaried employee",
    "i need a personal loan for home improvement",
    "my age is years old i work at a company",
    "i am applying for a loan amount of lakhs rupees",
    "my employment type is self employed and my income is",
    "i consent to the loan application process i agree",
    "i live in the city and need a loan for medical expenses",
]

# ─────────────────────────────────────────────────────────────────
# Build a tiny TF-IDF vocabulary at module load (pure stdlib + math)
# ─────────────────────────────────────────────────────────────────

def _tokenise(text: str) -> list[str]:
    return re.findall(r"\b[a-z]+\b", text.lower())


def _build_vocab(sentences: list[str]) -> dict[str, int]:
    vocab: dict[str, int] = {}
    for s in sentences:
        for tok in _tokenise(s):
            if tok not in vocab:
                vocab[tok] = len(vocab)
    return vocab


def _idf(sentences: list[str], vocab: dict[str, int]) -> list[float]:
    N = len(sentences)
    df = [0] * len(vocab)
    for s in sentences:
        seen = set(_tokenise(s))
        for tok in seen:
            if tok in vocab:
                df[vocab[tok]] += 1
    return [math.log((N + 1) / (d + 1)) + 1 for d in df]


def _tfidf_vector(text: str, vocab: dict[str, int], idf_vals: list[float]) -> list[float]:
    tokens = _tokenise(text)
    tf: dict[str, float] = {}
    for tok in tokens:
        tf[tok] = tf.get(tok, 0) + 1
    n = len(tokens) or 1
    vec = [0.0] * len(vocab)
    for tok, count in tf.items():
        if tok in vocab:
            vec[vocab[tok]] = (count / n) * idf_vals[vocab[tok]]
    return vec


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a)) or 1e-9
    mag_b = math.sqrt(x * x for x in b) if False else math.sqrt(sum(x * x for x in b)) or 1e-9
    return dot / (mag_a * mag_b)


# Pre-compute at import (fast — pure Python, no torch)
_VOCAB = _build_vocab(_LOAN_SENTENCES)
_IDF = _idf(_LOAN_SENTENCES, _VOCAB)
_LOAN_CENTROID: list[float] = [0.0] * len(_VOCAB)
for _s in _LOAN_SENTENCES:
    _vec = _tfidf_vector(_s, _VOCAB, _IDF)
    _LOAN_CENTROID = [_LOAN_CENTROID[i] + _vec[i] for i in range(len(_VOCAB))]
_n = len(_LOAN_SENTENCES)
_LOAN_CENTROID = [v / _n for v in _LOAN_CENTROID]


# ─────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────

SIMILARITY_THRESHOLD = 0.35  # cosine sim to loan centroid
MINIMUM_WORDS = 2             # ignore single-word utterances


def check_relevance(
    text: str,
    next_missing_field: Optional[str] = None,
) -> dict:
    """
    Determine whether `text` is relevant to a loan application.

    Returns
    -------
    dict with keys:
      is_relevant  : bool   — True  → let processing continue
      similarity   : float  — cosine similarity to loan-intent centroid
      matched_kw   : str | None — first keyword matched (if any)
      redirect_msg : str | None — None when relevant; redirect prompt otherwise
    """
    # Very short utterances (single words like "um", "uh", "ok") pass through
    tokens = _tokenise(text)
    if len(tokens) < MINIMUM_WORDS:
        return {"is_relevant": True, "similarity": 1.0, "matched_kw": None, "redirect_msg": None}

    # Tier 1 — keyword membership check (O(1) per word)
    text_lower = text.lower()
    matched_kw = next((kw for kw in LOAN_KEYWORDS if re.search(r"\b" + re.escape(kw) + r"\b", text_lower)), None)
    if matched_kw:
        return {"is_relevant": True, "similarity": 1.0, "matched_kw": matched_kw, "redirect_msg": None}

    # Tier 2 — bag-of-words cosine similarity
    user_vec = _tfidf_vector(text, _VOCAB, _IDF)
    sim = _cosine(user_vec, _LOAN_CENTROID)
    if sim >= SIMILARITY_THRESHOLD:
        return {"is_relevant": True, "similarity": round(sim, 3), "matched_kw": None, "redirect_msg": None}

    # Off-topic — build redirect message
    field_label = (next_missing_field or "your loan details").replace("_", " ")
    redirect_msg = (
        f"I can only assist with your loan application. "
        f"Could you tell me {field_label}?"
    )
    return {
        "is_relevant": False,
        "similarity": round(sim, 3),
        "matched_kw": None,
        "redirect_msg": redirect_msg,
    }


# ─────────────────────────────────────────────────────────────────
# REST endpoint
# ─────────────────────────────────────────────────────────────────

class GuardrailRequest(BaseModel):
    text: str
    next_missing_field: Optional[str] = None


@router.post("/check")
async def guardrail_check(req: GuardrailRequest):
    """Check whether applicant text is relevant to the loan interview."""
    return check_relevance(req.text, req.next_missing_field)
