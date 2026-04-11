"""
AgentFinance AI — FastAPI Backend Entry Point
Mounts all M01-M10 module routers and initializes services.
"""

import sys
import os

# Add backend directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from config import settings
from database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    # Startup
    print("[*] AgentFinance AI Backend starting...")
    await init_db()
    print(f"[+] Backend ready at http://localhost:{settings.BACKEND_PORT}")
    print(f"[+] Bureau Mock expected at {settings.BUREAU_MOCK_URL}")
    yield
    # Shutdown
    print("[-] Backend shutting down...")


app = FastAPI(
    title="AgentFinance AI",
    description="Agentic AI-powered retail loan onboarding platform — Airavat 3.0 Hackathon",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — Allow frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Permissive for hackathon
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ──────────────────────────────────────────────────────────────────
# Mount Module Routers
# ──────────────────────────────────────────────────────────────────

from modules.m01_session import router as m01_router
from modules.m02_stt import router as m02_router
from modules.m03_consent import router as m03_router
from modules.m04_vision import router as m04_router
from modules.m05_llm import router as m05_router
from modules.m06_fraud import router as m06_router
from modules.m07_bureau import router as m07_router
from modules.m08_offer import router as m08_router
from modules.m09_orchestrator import router as m09_router
from modules.m10_compliance import router as m10_router

app.include_router(m01_router)
app.include_router(m02_router)
app.include_router(m03_router)
app.include_router(m04_router)
app.include_router(m05_router)
app.include_router(m06_router)
app.include_router(m07_router)
app.include_router(m08_router)
app.include_router(m09_router)
app.include_router(m10_router)


# ──────────────────────────────────────────────────────────────────
# Health Check
# ──────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {
        "service": "AgentFinance AI",
        "version": "1.0.0",
        "status": "running",
        "modules": [
            "M01-Session", "M02-STT", "M03-Consent", "M04-Vision",
            "M05-LLM", "M06-Fraud", "M07-Bureau", "M08-Offer",
            "M09-Orchestrator", "M10-Compliance",
        ],
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}


# ──────────────────────────────────────────────────────────────────
# Run
# ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.BACKEND_HOST,
        port=settings.BACKEND_PORT,
        reload=True,
    )
