from fastapi import APIRouter

from markitdown_service import __version__
from markitdown_service.schemas import HealthResponse

router = APIRouter()


@router.get("/health")
async def health() -> HealthResponse:
    """Healthcheck del servicio."""
    return HealthResponse(status="ok", version=__version__, service="markitdown-service")
