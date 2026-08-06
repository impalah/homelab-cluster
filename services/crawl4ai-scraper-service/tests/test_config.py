"""Tests unitarios de Settings (pydantic-settings)."""

from __future__ import annotations

from crawl4ai_scraper_service.core.config import Settings, get_settings


def test_default_settings_values() -> None:
    settings = Settings(_env_file=None)

    assert settings.app_name == "Crawl4AI Scraper Service"
    assert settings.max_concurrent_scrapes == 12
    assert settings.enable_stealth_mode is False
    assert settings.enable_undetected_browser is False
    assert settings.enable_magic_mode is False
    assert settings.enable_proxy is False
    assert settings.proxy_configured is False
    assert settings.max_pages_before_recycle == 15


def test_log_level_is_normalized_to_uppercase() -> None:
    settings = Settings(_env_file=None, log_level="debug")
    assert settings.log_level == "DEBUG"


def test_proxy_configured_true_only_when_enabled_and_server_set() -> None:
    without_server = Settings(_env_file=None, enable_proxy=True)
    assert without_server.proxy_configured is False

    with_server = Settings(
        _env_file=None, enable_proxy=True, proxy_server="http://proxy.example.com:8080"
    )
    assert with_server.proxy_configured is True

    disabled = Settings(
        _env_file=None, enable_proxy=False, proxy_server="http://proxy.example.com:8080"
    )
    assert disabled.proxy_configured is False


def test_get_settings_is_cached() -> None:
    assert get_settings() is get_settings()


def test_settings_reads_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("MAX_CONCURRENT_SCRAPES", "25")
    monkeypatch.setenv("ENABLE_MAGIC_MODE", "true")

    settings = Settings(_env_file=None)

    assert settings.max_concurrent_scrapes == 25
    assert settings.enable_magic_mode is True
