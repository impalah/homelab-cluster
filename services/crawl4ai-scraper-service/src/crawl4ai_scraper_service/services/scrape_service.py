"""Lógica de negocio y orquestación del scraping.

Responsabilidades:
- Gestionar el semáforo de concurrencia (a través de `ScrapeConcurrencyLimiter`).
- Aplicar el timeout de scraping individual, evitando que una web lenta
  bloquee el semáforo indefinidamente.
- Delegar la ejecución real en la capa de repositorio (`ScraperRepository`),
  que es sustituible e inyectada por constructor.
- Transformar el resultado interno (`ScrapeResult`) en el modelo de
  respuesta HTTP (`ScrapeResponse`).
"""

from __future__ import annotations

import asyncio

from loguru import logger

from crawl4ai_scraper_service.domain.models import (
    ScrapeErrorCode,
    ScrapeMetadata,
    ScrapeParams,
    ScrapeResponse,
    ScrapeServiceError,
)
from crawl4ai_scraper_service.repositories.interfaces import ScraperRepository
from crawl4ai_scraper_service.services.concurrency import (
    ConcurrencyLimitTimeoutError,
    ScrapeConcurrencyLimiter,
)


class ScrapeService:
    """Orquesta el scraping aplicando control de concurrencia y timeouts."""

    def __init__(
        self,
        repository: ScraperRepository,
        limiter: ScrapeConcurrencyLimiter,
        scrape_timeout_seconds: float,
    ) -> None:
        self._repository = repository
        self._limiter = limiter
        self._scrape_timeout_seconds = scrape_timeout_seconds

    async def scrape_url(self, url: str, params: ScrapeParams | None = None) -> ScrapeResponse:
        """Ejecuta el scraping de `url` respetando concurrencia y timeout.

        `params`, si se indica, sobreescribe la configuración por defecto
        solo para esta petición — ver `ScrapeParams` y `Crawl4AIRepository`.

        Lanza `ScrapeServiceError` con el código adecuado si:
        - se agota el timeout de espera del semáforo (concurrencia al límite),
        - se agota el timeout individual de scraping,
        - o el repositorio informa de un fallo de scraping.
        """
        try:
            async with self._limiter.slot():
                logger.info(
                    "Iniciando scrape de {} ({}/{} slots activos){}",
                    url,
                    self._limiter.active_count + 1,
                    self._limiter.max_concurrent,
                    " con overrides" if params is not None else "",
                )
                result = await asyncio.wait_for(
                    self._repository.scrape(url, params),
                    timeout=self._scrape_timeout_seconds,
                )
        except ConcurrencyLimitTimeoutError as exc:
            logger.warning("Límite de concurrencia agotado para {}: {}", url, exc)
            raise ScrapeServiceError(ScrapeErrorCode.CONCURRENCY_LIMIT_EXCEEDED, str(exc)) from exc
        except TimeoutError as exc:
            logger.warning(
                "Timeout de scraping ({}s) agotado para {}",
                self._scrape_timeout_seconds,
                url,
            )
            raise ScrapeServiceError(
                ScrapeErrorCode.TIMEOUT,
                f"El scraping de {url} superó el timeout de {self._scrape_timeout_seconds}s",
            ) from exc
        except ScrapeServiceError:
            raise
        except Exception as exc:  # noqa: BLE001 - cualquier fallo inesperado del repositorio
            logger.exception("Error inesperado al scrapear {}", url)
            raise ScrapeServiceError(
                ScrapeErrorCode.SCRAPER_ERROR, f"Error inesperado del scraper: {exc}"
            ) from exc

        if not result.success:
            raise ScrapeServiceError(
                ScrapeErrorCode.SCRAPER_ERROR,
                result.error_message or "Error desconocido durante el scraping",
            )

        metadata = ScrapeMetadata(
            original_url=url,
            content_length=len(result.markdown),
            fallback_applied=result.fallback_applied,
            attempts=result.attempts,
            resolved_by=result.resolved_by,
            dedicated_browser=result.dedicated_browser,
        )
        return ScrapeResponse(markdown=result.markdown, metadata=metadata)
