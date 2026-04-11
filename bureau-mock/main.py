"""
AgentFinance AI — Mock Credit Bureau Service
Standalone FastAPI microservice (port 8001) that simulates a credit bureau.
Returns credit score, active loans, DPD history, and written-off accounts.
"""

import json
import os
import random
import asyncio
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

app = FastAPI(
    title="Mock Credit Bureau",
    description="Simulated credit bureau for AgentFinance AI hackathon",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ──────────────────────────────────────────────────────────────────
# Seed Data — 3 Demo Personas
# ──────────────────────────────────────────────────────────────────

SEED_DATA = {
    # Priya Sharma — Good credit, clean history → PASS
    "PRIYA001": {
        "applicant_id": "PRIYA001",
        "name": "Priya Sharma",
        "credit_score": 740,
        "active_loans": 1,
        "dpd_history": [0, 0, 0, 0, 0, 0],
        "written_off_accounts": 0,
        "credit_utilization": 0.25,
        "oldest_account_years": 8,
        "recent_inquiries": 1,
        "total_accounts": 5,
    },
    # Rohit Mehta — Bad credit, high risk → FAIL
    "ROHIT001": {
        "applicant_id": "ROHIT001",
        "name": "Rohit Mehta",
        "credit_score": 420,
        "active_loans": 6,
        "dpd_history": [0, 30, 60, 90, 120, 180],
        "written_off_accounts": 2,
        "credit_utilization": 0.92,
        "oldest_account_years": 3,
        "recent_inquiries": 8,
        "total_accounts": 10,
    },
    # Meera Patil — Borderline credit → REFER
    "MEERA001": {
        "applicant_id": "MEERA001",
        "name": "Meera Patil",
        "credit_score": 620,
        "active_loans": 3,
        "dpd_history": [0, 0, 15, 30, 0, 0],
        "written_off_accounts": 0,
        "credit_utilization": 0.55,
        "oldest_account_years": 5,
        "recent_inquiries": 3,
        "total_accounts": 7,
    },
}

# Also index by name (lowercase) for flexible lookup
NAME_INDEX = {}
for aid, data in SEED_DATA.items():
    name_key = data["name"].lower().replace(" ", "")
    NAME_INDEX[name_key] = aid
    # Also add first name
    first_name = data["name"].split()[0].lower()
    NAME_INDEX[first_name] = aid


def _generate_random_bureau() -> dict:
    """Generate random bureau data for unknown applicants."""
    score = random.randint(500, 800)
    return {
        "applicant_id": "UNKNOWN",
        "name": "Unknown Applicant",
        "credit_score": score,
        "active_loans": random.randint(0, 4),
        "dpd_history": [random.choice([0, 0, 0, 15, 30]) for _ in range(6)],
        "written_off_accounts": 0 if score > 600 else random.randint(0, 1),
        "credit_utilization": round(random.uniform(0.1, 0.7), 2),
        "oldest_account_years": random.randint(1, 10),
        "recent_inquiries": random.randint(0, 5),
        "total_accounts": random.randint(2, 8),
    }


# ──────────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────────

@app.get("/api/bureau/{applicant_id}")
async def get_bureau_data(applicant_id: str, delay_ms: int = 0):
    """
    Get credit bureau data for an applicant.
    
    Args:
        applicant_id: Applicant identifier (e.g. PRIYA001, or name like "priya")
        delay_ms: Simulated latency in milliseconds (for timeout testing)
    """
    # Simulate latency if requested
    if delay_ms > 0:
        await asyncio.sleep(delay_ms / 1000)
    
    # Try direct ID lookup
    applicant_id_upper = applicant_id.upper()
    if applicant_id_upper in SEED_DATA:
        return SEED_DATA[applicant_id_upper]
    
    # Try name-based lookup
    name_key = applicant_id.lower().replace(" ", "")
    if name_key in NAME_INDEX:
        return SEED_DATA[NAME_INDEX[name_key]]
    
    # Check if the name partially matches any persona
    for key, aid in NAME_INDEX.items():
        if key in name_key or name_key in key:
            return SEED_DATA[aid]
    
    # Unknown applicant — generate random
    data = _generate_random_bureau()
    data["applicant_id"] = applicant_id
    return data


@app.get("/api/bureau")
async def list_personas():
    """List all available bureau personas."""
    return {
        "personas": list(SEED_DATA.values()),
        "total": len(SEED_DATA),
    }


@app.get("/")
async def root():
    return {
        "service": "Mock Credit Bureau",
        "version": "1.0.0",
        "status": "running",
        "personas": list(SEED_DATA.keys()),
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}


if __name__ == "__main__":
    port = int(os.getenv("BUREAU_PORT", "8001"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
