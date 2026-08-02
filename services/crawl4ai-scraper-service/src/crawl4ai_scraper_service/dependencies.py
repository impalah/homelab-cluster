"""Proveedores de dependencias de FastAPI (`Depends`).

Desacopla los controllers de las implementaciones concretas de servicios y
repositorios: los controllers solo dependen de estas factorías, que a su
vez leen los singletons creados en el `lifespan` (`app.state`).
"""

from __future__ import annotations

from typing import cast

from fastapi import Depends, Request

from crawl4ai_scraper_service.core.config import Settings, get_settings
from crawl4ai_scraper_service.repositories.interfaces import ScraperRepository
from crawl4ai_scraper_service.services.concurrency import ScrapeConcurrencyLimiter
from crawl4ai_scraper_service.services.health_service import HealthService
from crawl4ai_scraper_service.services.scrape_service import ScrapeService


def get_scraper_repository(request: Request) -> ScraperRepository:
    """Devuelve la instancia singleton del repositorio de scraping."""
    # request.app.state es de tipo `Any` (Starlette no lo tipa) — cast()
    # documenta la garantía real: el lifespan (core/lifespan.py) es quien
    # deja este atributo con el tipo correcto antes de servir peticiones.
    return cast(ScraperRepository, request.app.state.scraper_repository)


def get_concurrency_limiter(request: Request) -> ScrapeConcurrencyLimiter:
    """Devuelve la instancia singleton del limitador de concurrencia."""
    return cast(ScrapeConcurrencyLimiter, request.app.state.concurrency_limiter)


def get_scrape_service(
    repository: ScraperRepository = Depends(get_scraper_repository),
    limiter: ScrapeConcurrencyLimiter = Depends(get_concurrency_limiter),
    settings: Settings = Depends(get_settings),
) -> ScrapeService:
    """Construye el `ScrapeService` inyectando repositorio, límites y settings."""
    return ScrapeService(
        repository=repository,
        limiter=limiter,
        scrape_timeout_seconds=settings.scrape_timeout_seconds,
    )


def get_health_service(
    repository: ScraperRepository = Depends(get_scraper_repository),
    limiter: ScrapeConcurrencyLimiter = Depends(get_concurrency_limiter),
) -> HealthService:
    """Construye el `HealthService` inyectando repositorio y límites."""
    return HealthService(repository=repository, limiter=limiter)
