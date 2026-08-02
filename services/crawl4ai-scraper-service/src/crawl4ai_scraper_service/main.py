"""Punto de entrada de la aplicación FastAPI."""

from __future__ import annotations

from fastapi import FastAPI

from crawl4ai_scraper_service.controllers.health_controller import router as health_router
from crawl4ai_scraper_service.controllers.scrape_controller import router as scrape_router
from crawl4ai_scraper_service.core.config import get_settings
from crawl4ai_scraper_service.core.lifespan import lifespan

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    description=(
        "Microservicio de scraping y limpieza de contenido web usando "
        "Crawl4AI, con control de concurrencia y estrategias anti-bot "
        "configurables."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(health_router)
app.include_router(scrape_router)


def run() -> None:
    """Punto de entrada para ejecución directa (`python -m crawl4ai_scraper_service.main`)."""
    import uvicorn

    uvicorn.run(
        "crawl4ai_scraper_service.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )


if __name__ == "__main__":
    run()
