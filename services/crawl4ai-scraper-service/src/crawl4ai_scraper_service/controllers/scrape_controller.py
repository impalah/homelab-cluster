"""Router de FastAPI para el endpoint de scraping.

Responsabilidad exclusiva: request/response HTTP y validación de entrada.
Toda la lógica de negocio se delega en `ScrapeService`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from loguru import logger

from crawl4ai_scraper_service.dependencies import get_scrape_service
from crawl4ai_scraper_service.domain.models import (
    ScrapeErrorCode,
    ScrapeRequest,
    ScrapeResponse,
    ScrapeServiceError,
)
from crawl4ai_scraper_service.services.scrape_service import ScrapeService

router = APIRouter(tags=["scrape"])

_ERROR_STATUS_MAP: dict[ScrapeErrorCode, int] = {
    ScrapeErrorCode.TIMEOUT: status.HTTP_504_GATEWAY_TIMEOUT,
    ScrapeErrorCode.CONCURRENCY_LIMIT_EXCEEDED: status.HTTP_503_SERVICE_UNAVAILABLE,
    ScrapeErrorCode.SCRAPER_ERROR: status.HTTP_502_BAD_GATEWAY,
    ScrapeErrorCode.UNKNOWN: status.HTTP_500_INTERNAL_SERVER_ERROR,
}


@router.post(
    "/scrape",
    response_model=ScrapeResponse,
    status_code=status.HTTP_200_OK,
    summary="Scrapea una URL y devuelve su markdown limpio",
)
async def scrape(
    payload: ScrapeRequest,
    service: ScrapeService = Depends(get_scrape_service),
) -> ScrapeResponse:
    """Ejecuta el pipeline de Crawl4AI sobre `payload.url` y devuelve el markdown.

    `payload.params`, si se indica, sobreescribe la configuración por
    defecto solo para esta petición — ver `ScrapeParams`.
    """
    try:
        return await service.scrape_url(str(payload.url), payload.params)
    except ScrapeServiceError as exc:
        http_status = _ERROR_STATUS_MAP.get(exc.code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        logger.error("Fallo al scrapear {}: [{}] {}", payload.url, exc.code, exc.message)
        raise HTTPException(status_code=http_status, detail=exc.message) from exc
