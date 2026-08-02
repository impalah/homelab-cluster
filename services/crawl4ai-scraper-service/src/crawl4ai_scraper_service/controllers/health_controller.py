"""Router de FastAPI para el endpoint de healthcheck."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from crawl4ai_scraper_service.dependencies import get_health_service
from crawl4ai_scraper_service.domain.models import HealthResponse
from crawl4ai_scraper_service.services.health_service import HealthService

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Estado del servicio y disponibilidad del navegador headless",
)
async def health(
    service: HealthService = Depends(get_health_service),
) -> HealthResponse:
    return await service.get_health()
