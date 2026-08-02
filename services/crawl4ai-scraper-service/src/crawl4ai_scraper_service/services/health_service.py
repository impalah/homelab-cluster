"""Lógica de negocio del healthcheck del servicio."""

from __future__ import annotations

from crawl4ai_scraper_service.domain.models import HealthResponse, ServiceStatus
from crawl4ai_scraper_service.repositories.interfaces import ScraperRepository
from crawl4ai_scraper_service.services.concurrency import ScrapeConcurrencyLimiter


class HealthService:
    """Calcula el estado de salud del servicio combinando repositorio y límites."""

    def __init__(self, repository: ScraperRepository, limiter: ScrapeConcurrencyLimiter) -> None:
        self._repository = repository
        self._limiter = limiter

    async def get_health(self) -> HealthResponse:
        browser_ready = await self._repository.is_ready()
        status = ServiceStatus.OK if browser_ready else ServiceStatus.DEGRADED
        return HealthResponse(
            status=status,
            browser_ready=browser_ready,
            active_scrapes=self._limiter.active_count,
            max_concurrent_scrapes=self._limiter.max_concurrent,
        )
