"""
AgentFinance AI — Configuration
Loads all settings from environment variables with sensible defaults.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_env_path)


class Settings:
    # --- Backend ---
    BACKEND_HOST: str = os.getenv("BACKEND_HOST", "0.0.0.0")
    BACKEND_PORT: int = int(os.getenv("BACKEND_PORT", "8000"))
    BUREAU_MOCK_URL: str = os.getenv("BUREAU_MOCK_URL", "http://localhost:8001")

    # --- Auth ---
    JWT_SECRET: str = os.getenv("JWT_SECRET", "agentfinance-hackathon-secret-key-change-me")
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRY_MINUTES: int = 60

    # --- Database ---
    DATABASE_PATH: str = os.getenv("DATABASE_PATH", "./data/agentfinance.db")

    # --- LLM ---
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")

    @property
    def has_groq_key(self) -> bool:
        return bool(self.GROQ_API_KEY) and not self.GROQ_API_KEY.startswith("gsk_your_")
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

    # --- STT ---
    WHISPER_MODEL: str = os.getenv("WHISPER_MODEL", "base.en")
    WHISPER_DEVICE: str = os.getenv("WHISPER_DEVICE", "cpu")
    WHISPER_COMPUTE_TYPE: str = os.getenv("WHISPER_COMPUTE_TYPE", "int8")

    # --- Vision ---
    LIVENESS_THRESHOLD: float = float(os.getenv("LIVENESS_THRESHOLD", "0.6"))
    AGE_DELTA_THRESHOLD: int = int(os.getenv("AGE_DELTA_THRESHOLD", "10"))
    FRAME_CAPTURE_INTERVAL_MS: int = int(os.getenv("FRAME_CAPTURE_INTERVAL_MS", "3000"))

    # --- Fraud ---
    FRAUD_HIGH_THRESHOLD: int = int(os.getenv("FRAUD_HIGH_THRESHOLD", "60"))
    FRAUD_MEDIUM_THRESHOLD: int = int(os.getenv("FRAUD_MEDIUM_THRESHOLD", "30"))
    VELOCITY_WINDOW_MINUTES: int = int(os.getenv("VELOCITY_WINDOW_MINUTES", "60"))
    MAX_SESSIONS_PER_DEVICE: int = int(os.getenv("MAX_SESSIONS_PER_DEVICE", "3"))

    # --- GeoIP ---
    GEOIP_API_URL: str = os.getenv("GEOIP_API_URL", "http://ip-api.com/json")

    # --- Frontend (for CORS) ---
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:3000")


settings = Settings()
