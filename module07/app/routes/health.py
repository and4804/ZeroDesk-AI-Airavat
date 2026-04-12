"""
Health check endpoint for the Mock Bureau service.
"""

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check():
    """Service health probe — used by docker-compose and orchestrator."""
    return {
        "status": "healthy",
        "service": "bureau-mock",
        "module": "M07",
        "version": "1.0.0",
    }
