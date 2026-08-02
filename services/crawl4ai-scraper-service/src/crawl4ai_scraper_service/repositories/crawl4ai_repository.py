"""Adaptador concreto sobre Crawl4AI.

Implementa `ScraperRepository` encapsulando toda la interacción con la
librería Crawl4AI: inicialización/cierre del navegador (singleton
reutilizable), ejecución de la petición de scraping y mapeo de la
respuesta de Crawl4AI a `ScrapeResult` (modelo de dominio interno).

Esta clase es la única de la aplicación que importa `crawl4ai`
directamente; el resto del código (servicios, controllers) solo conoce
la interfaz `ScraperRepository` y los modelos de dominio.

## Overrides por petición (`ScrapeParams`)

`magic_mode`/`wait_until`/`page_timeout_ms`/`word_count_threshold`/
`max_retries` son configuración de **ejecución** (`CrawlerRunConfig`) — se
pueden variar en cada llamada a `crawler.arun()` sin coste extra, así que
un override simplemente reconstruye el `CrawlerRunConfig` para esa
petición y reutiliza el navegador compartido.

`stealth_mode`/`undetected_browser` son configuración de **navegador**
(`BrowserConfig` + estrategia del crawler) — se fija al lanzar Chromium, no
por petición. Cuando su valor efectivo difiere del configurado en el
despliegue, esta clase lanza un navegador Chromium **dedicado**, solo para
esa petición, a través de `_dedicated_browser_limiter` (un semáforo
separado del de concurrencia general — cada uno es un proceso Chromium
completo, hay que limitar cuántos se lanzan a la vez para no agotar la RAM
en nodos pequeños como una Raspberry Pi).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from loguru import logger

from crawl4ai_scraper_service.core.config import Settings
from crawl4ai_scraper_service.core.crawler_config import (
    Crawl4AIConfigBundle,
    build_crawl4ai_config,
    build_run_config,
)
from crawl4ai_scraper_service.domain.models import ScrapeParams, ScrapeResult
from crawl4ai_scraper_service.services.concurrency import ScrapeConcurrencyLimiter

if TYPE_CHECKING:
    from crawl4ai import AsyncWebCrawler

# Traduce los nombres de campo de ScrapeParams (contrato HTTP) a los nombres
# de campo reales de Settings — así el resto de la lógica solo trabaja con
# Settings.model_copy(update=...), sin duplicar valores por defecto ni
# lógica de construcción de configuración de Crawl4AI (ver crawler_config.py).
_PARAM_TO_SETTINGS_FIELD: Final[dict[str, str]] = {
    "stealth_mode": "enable_stealth_mode",
    "undetected_browser": "enable_undetected_browser",
    "magic_mode": "enable_magic_mode",
    "wait_until": "crawler_wait_until",
    "page_timeout_ms": "crawler_page_timeout_ms",
    "word_count_threshold": "markdown_word_count_threshold",
    "max_retries": "max_retries",
}

# Subconjunto de los anteriores que son de nivel NAVEGADOR (no de ejecución)
# — si su valor efectivo difiere del de Settings, hace falta un navegador
# dedicado. Ver docstring del módulo.
_BROWSER_LEVEL_SETTINGS_FIELDS: Final[tuple[str, ...]] = (
    "enable_stealth_mode",
    "enable_undetected_browser",
)


class Crawl4AIRepository:
    """Implementación de `ScraperRepository` basada en Crawl4AI + Playwright."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._config: Crawl4AIConfigBundle = build_crawl4ai_config(settings)
        self._crawler: AsyncWebCrawler | None = None
        self._ready = False
        self._dedicated_browser_limiter = ScrapeConcurrencyLimiter(
            max_concurrent=settings.max_concurrent_dedicated_browsers,
            acquire_timeout_seconds=settings.semaphore_acquire_timeout_seconds,
        )

    async def start(self) -> None:
        """Lanza el navegador headless de Crawl4AI y lo deja listo para reutilizar."""
        from crawl4ai import AsyncWebCrawler

        if self._crawler is not None:
            return

        crawler_kwargs: dict = {"config": self._config.browser_config}
        if self._config.crawler_strategy is not None:
            crawler_kwargs["crawler_strategy"] = self._config.crawler_strategy

        logger.info("Inicializando navegador de Crawl4AI...")
        self._crawler = AsyncWebCrawler(**crawler_kwargs)
        await self._crawler.start()
        self._ready = True
        logger.info("Navegador de Crawl4AI inicializado y listo")

    async def stop(self) -> None:
        """Cierra el navegador y libera recursos."""
        if self._crawler is None:
            return
        logger.info("Cerrando navegador de Crawl4AI...")
        await self._crawler.close()
        self._crawler = None
        self._ready = False

    async def is_ready(self) -> bool:
        """True si el navegador está inicializado y disponible."""
        return self._ready and self._crawler is not None

    async def scrape(self, url: str, params: ScrapeParams | None = None) -> ScrapeResult:
        """Ejecuta el pipeline de Crawl4AI sobre `url` y mapea el resultado.

        Devuelve un `ScrapeResult` con `success=True` y el markdown limpio si
        todo fue bien, o `success=False` con `error_message` en caso de fallo
        (incluyendo bloqueos detectados por Crawl4AI tras agotar reintentos).

        `params`, si se indica, sobreescribe la configuración de esta
        petición únicamente — ver el docstring del módulo para la
        distinción entre overrides "de ejecución" (navegador compartido) y
        "de navegador" (navegador dedicado).
        """
        overrides = self._build_overrides(params)

        if not overrides:
            if self._crawler is None:
                raise RuntimeError(
                    "El repositorio de Crawl4AI no está inicializado. "
                    "Llama a start() antes de scrape()."
                )
            result = await self._crawler.arun(url=url, config=self._config.run_config)
            return self._map_result(url, result)

        effective_settings = self._settings.model_copy(update=overrides)

        if not self._needs_dedicated_browser(overrides):
            if self._crawler is None:
                raise RuntimeError(
                    "El repositorio de Crawl4AI no está inicializado. "
                    "Llama a start() antes de scrape()."
                )
            run_config = build_run_config(effective_settings)
            result = await self._crawler.arun(url=url, config=run_config)
            return self._map_result(url, result)

        return await self._scrape_with_dedicated_browser(url, effective_settings)

    @staticmethod
    def _build_overrides(params: ScrapeParams | None) -> dict[str, Any]:
        """Traduce los campos no-`None` de `ScrapeParams` a nombres de campo de `Settings`."""
        if params is None:
            return {}
        overrides: dict[str, Any] = {}
        for request_field, settings_field in _PARAM_TO_SETTINGS_FIELD.items():
            value = getattr(params, request_field)
            if value is not None:
                overrides[settings_field] = value
        return overrides

    def _needs_dedicated_browser(self, overrides: dict[str, Any]) -> bool:
        """True si algún override de nivel navegador difiere del valor ya desplegado."""
        return any(
            field in overrides and overrides[field] != getattr(self._settings, field)
            for field in _BROWSER_LEVEL_SETTINGS_FIELDS
        )

    async def _scrape_with_dedicated_browser(
        self, url: str, effective_settings: Settings
    ) -> ScrapeResult:
        """Lanza un navegador Chromium dedicado solo para esta petición.

        Limitado por `_dedicated_browser_limiter` (`MAX_CONCURRENT_DEDICATED_BROWSERS`,
        2 por defecto) — cada uno es un proceso Chromium completo, no el
        navegador compartido del servicio.
        """
        from crawl4ai import AsyncWebCrawler

        async with self._dedicated_browser_limiter.slot():
            bundle = build_crawl4ai_config(effective_settings)
            crawler_kwargs: dict = {"config": bundle.browser_config}
            if bundle.crawler_strategy is not None:
                crawler_kwargs["crawler_strategy"] = bundle.crawler_strategy

            logger.info(
                "Lanzando navegador dedicado para {} (stealth={}, undetected={})...",
                url,
                effective_settings.enable_stealth_mode,
                effective_settings.enable_undetected_browser,
            )
            dedicated_crawler = AsyncWebCrawler(**crawler_kwargs)
            try:
                await dedicated_crawler.start()
                result = await dedicated_crawler.arun(url=url, config=bundle.run_config)
                return self._map_result(url, result, dedicated_browser=True)
            finally:
                await dedicated_crawler.close()
                logger.info("Navegador dedicado para {} cerrado", url)

    @staticmethod
    def _map_result(url: str, result: Any, *, dedicated_browser: bool = False) -> ScrapeResult:
        """Mapea un `CrawlResult` de Crawl4AI al modelo de dominio `ScrapeResult`."""
        crawl_stats = getattr(result, "crawl_stats", None) or {}
        attempts = crawl_stats.get("attempts", 1)
        resolved_by = crawl_stats.get("resolved_by")
        fallback_applied = bool(crawl_stats.get("fallback_fetch_used", False) or attempts > 1)

        if not getattr(result, "success", False):
            error_message = getattr(result, "error_message", None) or "Scraping falló"
            logger.warning("Scrape fallido para {}: {}", url, error_message)
            return ScrapeResult(
                success=False,
                markdown="",
                error_message=error_message,
                fallback_applied=fallback_applied,
                attempts=attempts,
                resolved_by=resolved_by,
                dedicated_browser=dedicated_browser,
            )

        markdown_obj = getattr(result, "markdown", "") or ""
        # `result.markdown` puede ser un str o un objeto MarkdownGenerationResult
        # con `.raw_markdown` / `.fit_markdown`, según la versión de Crawl4AI.
        markdown_text = (
            getattr(markdown_obj, "fit_markdown", None)
            or getattr(markdown_obj, "raw_markdown", None)
            or (markdown_obj if isinstance(markdown_obj, str) else str(markdown_obj))
        )

        return ScrapeResult(
            success=True,
            markdown=markdown_text,
            error_message=None,
            fallback_applied=fallback_applied,
            attempts=attempts,
            resolved_by=resolved_by,
            dedicated_browser=dedicated_browser,
        )
