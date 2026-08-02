"""Tests del endpoint GET /health."""

from __future__ import annotations

from fastapi.testclient import TestClient

from crawl4ai_scraper_service.core.config import Settings
from crawl4ai_scraper_service.services.concurrency import ScrapeConcurrencyLimiter
from tests.conftest import FakeScraperRepository, build_test_app


def test_health_ok_when_browser_ready(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["browser_ready"] is True
    assert body["max_concurrent_scrapes"] == 5
    assert body["active_scrapes"] == 0


def test_health_degraded_when_browser_not_ready() -> None:
    repository = FakeScraperRepository(ready=False)
    limiter = ScrapeConcurrencyLimiter(max_concurrent=3)
    app = build_test_app(repository, limiter, Settings())
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["browser_ready"] is False
