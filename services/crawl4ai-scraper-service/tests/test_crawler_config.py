"""Tests de construcción dinámica de la configuración de Crawl4AI.

Usan las clases reales de la librería `crawl4ai` (construcción de objetos de
configuración es pura Python, no requiere lanzar un navegador real).
"""

from __future__ import annotations

from crawl4ai import BrowserConfig, CrawlerRunConfig
from crawl4ai.async_crawler_strategy import AsyncPlaywrightCrawlerStrategy

from crawl4ai_scraper_service.core.config import Settings
from crawl4ai_scraper_service.core.crawler_config import (
    build_browser_config,
    build_crawl4ai_config,
    build_crawler_strategy,
    build_run_config,
)


def test_build_browser_config_defaults() -> None:
    settings = Settings(_env_file=None)
    browser_config = build_browser_config(settings)

    assert isinstance(browser_config, BrowserConfig)
    assert browser_config.headless is True
    assert browser_config.enable_stealth is False


def test_build_browser_config_enables_stealth() -> None:
    settings = Settings(_env_file=None, enable_stealth_mode=True)
    browser_config = build_browser_config(settings)

    assert browser_config.enable_stealth is True


def test_build_browser_config_applies_proxy() -> None:
    settings = Settings(
        _env_file=None,
        enable_proxy=True,
        proxy_server="http://proxy.example.com:8080",
        proxy_username="user",
        proxy_password="pass",
    )
    browser_config = build_browser_config(settings)

    assert browser_config.proxy_config is not None
    assert browser_config.proxy_config.server == "http://proxy.example.com:8080"
    assert browser_config.proxy_config.username == "user"


def test_build_crawler_strategy_none_when_undetected_disabled() -> None:
    settings = Settings(_env_file=None, enable_undetected_browser=False)
    browser_config = build_browser_config(settings)

    strategy = build_crawler_strategy(settings, browser_config)

    assert strategy is None


def test_build_crawler_strategy_returns_undetected_adapter_strategy() -> None:
    settings = Settings(_env_file=None, enable_undetected_browser=True)
    browser_config = build_browser_config(settings)

    strategy = build_crawler_strategy(settings, browser_config)

    assert isinstance(strategy, AsyncPlaywrightCrawlerStrategy)


def test_build_run_config_defaults() -> None:
    settings = Settings(_env_file=None)
    run_config = build_run_config(settings)

    assert isinstance(run_config, CrawlerRunConfig)
    assert run_config.magic is False
    assert run_config.simulate_user is False
    assert run_config.override_navigator is False
    assert run_config.max_retries == settings.max_retries
    assert run_config.proxy_config is None


def test_build_run_config_enables_magic_mode() -> None:
    settings = Settings(_env_file=None, enable_magic_mode=True)
    run_config = build_run_config(settings)

    assert run_config.magic is True
    assert run_config.simulate_user is True
    assert run_config.override_navigator is True


def test_build_run_config_applies_proxy_config() -> None:
    settings = Settings(
        _env_file=None,
        enable_proxy=True,
        proxy_server="http://residential-proxy.example.com:9090",
    )
    run_config = build_run_config(settings)

    assert run_config.proxy_config is not None
    assert run_config.proxy_config.server == "http://residential-proxy.example.com:9090"


def test_build_crawl4ai_config_bundle() -> None:
    settings = Settings(_env_file=None, enable_undetected_browser=True)
    bundle = build_crawl4ai_config(settings)

    assert isinstance(bundle.browser_config, BrowserConfig)
    assert isinstance(bundle.run_config, CrawlerRunConfig)
    assert isinstance(bundle.crawler_strategy, AsyncPlaywrightCrawlerStrategy)
