"""Tests del punto de entrada de la aplicación (app/main.py)."""

from __future__ import annotations

from crawl4ai_scraper_service.core.config import get_settings
from crawl4ai_scraper_service.main import app, run


def test_app_is_configured_with_expected_metadata() -> None:
    settings = get_settings()
    assert app.title == settings.app_name

    openapi_paths = set(app.openapi()["paths"].keys())
    assert "/scrape" in openapi_paths
    assert "/health" in openapi_paths


def test_run_starts_uvicorn_with_expected_arguments(monkeypatch) -> None:
    captured: dict = {}

    def fake_run(target: str, **kwargs) -> None:
        captured["target"] = target
        captured.update(kwargs)

    monkeypatch.setattr("uvicorn.run", fake_run)

    run()

    assert captured["target"] == "crawl4ai_scraper_service.main:app"
    settings = get_settings()
    assert captured["host"] == settings.host
    assert captured["port"] == settings.port
