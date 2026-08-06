"""Construcción dinámica de la configuración de Crawl4AI a partir de Settings.

Este módulo es el único punto donde los `Settings` de pydantic-settings se
traducen a los objetos de configuración nativos de Crawl4AI
(`BrowserConfig`, `CrawlerRunConfig`, `ProxyConfig`). Nada de esto está
hardcodeado: cada flag de anti-detección se activa/desactiva de forma
independiente según la configuración de entorno.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from loguru import logger

from crawl4ai_scraper_service.core.config import Settings

if TYPE_CHECKING:
    from crawl4ai import BrowserConfig, CrawlerRunConfig
    from crawl4ai.async_crawler_strategy import AsyncCrawlerStrategy


@dataclass(frozen=True, slots=True)
class Crawl4AIConfigBundle:
    """Agrupa toda la configuración de Crawl4AI resuelta para esta app.

    Se construye una única vez a partir de `Settings` y se reutiliza tanto
    para inicializar el navegador (browser_config / crawler_strategy) como
    para configurar cada ejecución de scraping (run_config).
    """

    browser_config: BrowserConfig
    run_config: CrawlerRunConfig
    crawler_strategy: AsyncCrawlerStrategy | None


def build_browser_config(settings: Settings) -> BrowserConfig:
    """Construye el `BrowserConfig` de Crawl4AI según los settings de la app.

    Controla el modo headless, verbosidad y el flag de stealth mode
    (`ENABLE_STEALTH_MODE`), que parchea `navigator.webdriver`, fingerprint
    de canvas/WebGL, etc.
    """
    from crawl4ai import BrowserConfig

    kwargs: dict = {
        "headless": settings.crawler_headless,
        "verbose": settings.crawler_verbose,
        "enable_stealth": settings.enable_stealth_mode,
        "max_pages_before_recycle": settings.max_pages_before_recycle,
    }

    if settings.proxy_configured:
        proxy_dict: dict = {"server": settings.proxy_server}
        if settings.proxy_username:
            proxy_dict["username"] = settings.proxy_username
        if settings.proxy_password:
            proxy_dict["password"] = settings.proxy_password
        kwargs["proxy_config"] = proxy_dict

    return BrowserConfig(**kwargs)


def build_crawler_strategy(
    settings: Settings, browser_config: BrowserConfig
) -> AsyncCrawlerStrategy | None:
    """Construye la estrategia del crawler, activando Undetected Browser si aplica.

    Cuando `ENABLE_UNDETECTED_BROWSER` está activo, se sustituye el adapter
    de Playwright por defecto por `UndetectedAdapter`, que aplica parches de
    evasión adicionales para sistemas de detección avanzados (Cloudflare,
    DataDome, Akamai, etc.). Devuelve `None` cuando no aplica, en cuyo caso
    Crawl4AI usa su estrategia por defecto.
    """
    if not settings.enable_undetected_browser:
        return None

    from crawl4ai import UndetectedAdapter
    from crawl4ai.async_crawler_strategy import AsyncPlaywrightCrawlerStrategy

    logger.debug("Undetected Browser Adapter activado")
    adapter = UndetectedAdapter()
    return AsyncPlaywrightCrawlerStrategy(browser_config=browser_config, browser_adapter=adapter)


def build_run_config(settings: Settings) -> CrawlerRunConfig:
    """Construye el `CrawlerRunConfig` por defecto para cada ejecución de scrape.

    Incorpora Magic Mode (`ENABLE_MAGIC_MODE`), la política de reintentos
    ante bloqueo (`MAX_RETRIES`) y el proxy de retry/escalada
    (`ENABLE_PROXY`), además de los parámetros de generación de markdown.
    """
    from crawl4ai import CacheMode, CrawlerRunConfig
    from crawl4ai.content_filter_strategy import PruningContentFilter
    from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator

    magic = settings.enable_magic_mode

    kwargs: dict = {
        "cache_mode": CacheMode.BYPASS,
        "wait_until": settings.crawler_wait_until,
        "page_timeout": settings.crawler_page_timeout_ms,
        "word_count_threshold": settings.markdown_word_count_threshold,
        "magic": magic,
        "simulate_user": magic,
        "override_navigator": magic,
        "remove_overlay_elements": True,
        "max_retries": settings.max_retries,
        "markdown_generator": DefaultMarkdownGenerator(content_filter=PruningContentFilter()),
        "verbose": settings.crawler_verbose,
    }

    if settings.proxy_configured:
        from crawl4ai.async_configs import ProxyConfig

        proxy_kwargs: dict = {"server": settings.proxy_server}
        if settings.proxy_username:
            proxy_kwargs["username"] = settings.proxy_username
        if settings.proxy_password:
            proxy_kwargs["password"] = settings.proxy_password
        kwargs["proxy_config"] = ProxyConfig(**proxy_kwargs)

    return CrawlerRunConfig(**kwargs)


def build_crawl4ai_config(settings: Settings) -> Crawl4AIConfigBundle:
    """Punto único de construcción de toda la configuración de Crawl4AI.

    Traduce dinámicamente los `Settings` de la aplicación (variables de
    entorno) al conjunto de objetos de configuración nativos que Crawl4AI
    necesita, sin valores hardcodeados.
    """
    browser_config = build_browser_config(settings)
    crawler_strategy = build_crawler_strategy(settings, browser_config)
    run_config = build_run_config(settings)

    logger.info(
        "Configuración de Crawl4AI construida: stealth={}, undetected={}, "
        "magic={}, proxy={}, max_retries={}",
        settings.enable_stealth_mode,
        settings.enable_undetected_browser,
        settings.enable_magic_mode,
        settings.proxy_configured,
        settings.max_retries,
    )

    return Crawl4AIConfigBundle(
        browser_config=browser_config,
        run_config=run_config,
        crawler_strategy=crawler_strategy,
    )
