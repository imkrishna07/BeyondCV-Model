"""Route registration for the service API."""

from fastapi import APIRouter

from app.schemas.health import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["health"])
def health_check() -> HealthResponse:
    """Report whether the AI service is accepting requests."""
    return HealthResponse(status="ok", service="beyondcv-ai")
