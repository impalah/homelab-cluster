"""Tests del endpoint POST /scrape (capa de controller, con servicios reales
pero infraestructura de Crawl4AI mockeada vía FakeScraperRepository)."""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from crawl4ai_scraper_service.core.config import Settings
from crawl4ai_scraper_service.domain.models import ScrapeResult
from crawl4ai_scraper_service.services.concurrency import ScrapeConcurrencyLimiter
from tests.conftest import FakeScraperRepository, build_test_app


def test_scrape_success(client: TestClient, fake_repository: FakeScraperRepository) -> None:
    response = client.post("/scrape", json={"url": "https://example.com"})

    assert response.status_code == 200
    body = response.json()
    assert body["markdown"] == fake_repository.result.markdown
    assert body["metadata"]["content_length"] == len(fake_repository.result.markdown)
    assert body["metadata"]["fallback_applied"] is False
    assert body["metadata"]["attempts"] == 1
    assert body["metadata"]["resolved_by"] == "direct"
    assert fake_repository.calls == ["https://example.com/"]


def test_scrape_invalid_url_returns_422(client: TestClient) -> None:
    response = client.post("/scrape", json={"url": "not-a-valid-url"})

    assert response.status_code == 422


def test_scrape_missing_url_returns_422(client: TestClient) -> None:
    response = client.post("/scrape", json={})

    assert response.status_code == 422


def test_scrape_without_params_forwards_none(
    client: TestClient, fake_repository: FakeScraperRepository
) -> None:
    response = client.post("/scrape", json={"url": "https://example.com"})

    assert response.status_code == 200
    assert fake_repository.params_received == [None]


def test_scrape_with_params_forwards_them_to_repository(
    client: TestClient, fake_repository: FakeScraperRepository
) -> None:
    response = client.post(
        "/scrape",
        json={
            "url": "https://example.com",
            "params": {"stealth_mode": True, "wait_until": "networkidle"},
        },
    )

    assert response.status_code == 200
    received = fake_repository.params_received[0]
    assert received is not None
    assert received.stealth_mode is True
    assert received.wait_until == "networkidle"


def test_scrape_with_string_boolean_param_is_coerced(
    client: TestClient, fake_repository: FakeScraperRepository
) -> None:
    """Igual que el ejemplo real de uso: {"stealth_mode": "true"} (string, no bool)."""
    response = client.post(
        "/scrape",
        json={"url": "https://example.com", "params": {"stealth_mode": "true"}},
    )

    assert response.status_code == 200
    assert fake_repository.params_received[0].stealth_mode is True


def test_scrape_with_unknown_param_returns_422(client: TestClient) -> None:
    response = client.post(
        "/scrape",
        json={"url": "https://example.com", "params": {"stealh_mode": True}},  # typo a propósito
    )

    assert response.status_code == 422


def test_scrape_with_invalid_wait_until_returns_422(client: TestClient) -> None:
    response = client.post(
        "/scrape",
        json={"url": "https://example.com", "params": {"wait_until": "instantaneous"}},
    )

    assert response.status_code == 422


def test_scrape_scraper_error_returns_502() -> None:
    repository = FakeScraperRepository(
        result=ScrapeResult(success=False, error_message="Bloqueado por Cloudflare")
    )
    limiter = ScrapeConcurrencyLimiter(max_concurrent=3)
    app = build_test_app(repository, limiter, Settings())
    client = TestClient(app)

    response = client.post("/scrape", json={"url": "https://blocked.example.com"})

    assert response.status_code == 502
    assert "Bloqueado por Cloudflare" in response.json()["detail"]


def test_scrape_timeout_returns_504() -> None:
    repository = FakeScraperRepository(delay_seconds=0.3)
    limiter = ScrapeConcurrencyLimiter(max_concurrent=3)
    settings = Settings(scrape_timeout_seconds=0.05)
    app = build_test_app(repository, limiter, settings)
    client = TestClient(app)

    response = client.post("/scrape", json={"url": "https://slow.example.com"})

    assert response.status_code == 504


@pytest.mark.asyncio
async def test_scrape_concurrency_limit_returns_503() -> None:
    """Con 1 slot y un scrape lento, la segunda petición concurrente debe
    agotar el timeout de espera del semáforo y recibir un 503."""
    repository = FakeScraperRepository(delay_seconds=0.4)
    limiter = ScrapeConcurrencyLimiter(max_concurrent=1, acquire_timeout_seconds=0.1)
    settings = Settings(scrape_timeout_seconds=5.0)
    app = build_test_app(repository, limiter, settings)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        first = asyncio.create_task(ac.post("/scrape", json={"url": "https://slow.example.com/a"}))
        await asyncio.sleep(0.02)  # asegura que 'first' ya adquirió el slot
        second = asyncio.create_task(ac.post("/scrape", json={"url": "https://slow.example.com/b"}))

        first_response, second_response = await asyncio.gather(first, second)

    assert first_response.status_code == 200
    assert second_response.status_code == 503
