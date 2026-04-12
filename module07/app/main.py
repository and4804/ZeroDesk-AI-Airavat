"""
AgentFinance AI — Mock Bureau & Eligibility Engine (M07)

Standalone FastAPI microservice on port 8001.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import HOST, PORT, load_rules_config, load_seed_data
from app.routes import bureau, docs, health, mocks


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Pre-load seed data and rules config at startup."""
    seed = load_seed_data()
    rules = load_rules_config()
    print(f"[M07] Loaded {len(seed)} seed profiles, {len(rules)} eligibility rules")
    yield


app = FastAPI(
    title="AgentFinance AI — Mock Bureau (M07)",
    description=(
        "Isolated mock credit bureau microservice.  "
        "Simulates CIBIL-style bureau lookups and runs a configurable "
        "policy rules engine (R01–R08) for eligibility decisioning."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# ── CORS (allow frontend at :3000 and backend at :8000) ──────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Register routers ─────────────────────────────────────────────────
app.include_router(health.router)
app.include_router(bureau.router)
app.include_router(mocks.router)
app.include_router(docs.router)


# ── Entrypoint ────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=HOST,
        port=PORT,
        reload=True,
    )
