"""Ciclo de vida (lifespan) de la aplicación FastAPI.

Inicializa de forma singleton y reutilizable el navegador de Crawl4AI (a
través de `Crawl4AIRepository`) y el limitador de concurrencia al arrancar
la aplicación, y los libera correctamente al apagarla.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from loguru import logger

from crawl4ai_scraper_service.core.config import get_settings
from crawl4ai_scraper_service.core.logging import configure_logging
from crawl4ai_scraper_service.repositories.crawl4ai_repository import Crawl4AIRepository
from crawl4ai_scraper_service.services.concurrency import ScrapeConcurrencyLimiter


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Gestiona el arranque/apagado de recursos compartidos de la aplicación."""
    settings = get_settings()
    configure_logging(settings)
    logger.info("Arrancando {} (env={})", settings.app_name, settings.app_env)

    repository = Crawl4AIRepository(settings)
    await repository.start()

    limiter = ScrapeConcurrencyLimiter(
        max_concurrent=settings.max_concurrent_scrapes,
        acquire_timeout_seconds=settings.semaphore_acquire_timeout_seconds,
    )

    app.state.settings = settings
    app.state.scraper_repository = repository
    app.state.concurrency_limiter = limiter

    logger.info(
        "Servicio listo (max_concurrent_scrapes={}, scrape_timeout_seconds={})",
        settings.max_concurrent_scrapes,
        settings.scrape_timeout_seconds,
    )

    try:
        yield
    finally:
        logger.info("Apagando {}...", settings.app_name)
        await repository.stop()
        logger.info("Recursos liberados correctamente")
