from fastapi import APIRouter

from whisper_service import __version__
from whisper_service.config import settings
from whisper_service.schemas import HealthResponse

router = APIRouter()


@router.get("/health")
async def health() -> HealthResponse:
    """Healthcheck del servicio."""
    return HealthResponse(
        status="ok",
        version=__version__,
        service="whisper-service",
        model=settings.whisper_model,
        device=settings.whisper_device,
        compute_type=settings.whisper_compute_type,
        language=settings.whisper_language,
    )
