"""Tests unitarios de ScrapeService (mockeando la capa de infraestructura)."""

from __future__ import annotations

import asyncio

import pytest

from crawl4ai_scraper_service.domain.models import (
    ScrapeErrorCode,
    ScrapeParams,
    ScrapeResult,
    ScrapeServiceError,
)
from crawl4ai_scraper_service.services.concurrency import ScrapeConcurrencyLimiter
from crawl4ai_scraper_service.services.scrape_service import ScrapeService
from tests.conftest import FakeScraperRepository


@pytest.mark.asyncio
async def test_scrape_url_success_transforms_result() -> None:
    repository = FakeScraperRepository(
        result=ScrapeResult(
            success=True,
            markdown="contenido limpio",
            attempts=2,
            fallback_applied=True,
            resolved_by="proxy",
        )
    )
    limiter = ScrapeConcurrencyLimiter(max_concurrent=2)
    service = ScrapeService(repository, limiter, scrape_timeout_seconds=5.0)

    response = await service.scrape_url("https://example.com")

    assert response.markdown == "contenido limpio"
    assert response.metadata.original_url == "https://example.com"
    assert response.metadata.content_length == len("contenido limpio")
    assert response.metadata.fallback_applied is True
    assert response.metadata.attempts == 2
    assert response.metadata.resolved_by == "proxy"


@pytest.mark.asyncio
async def test_scrape_url_passes_params_through_to_repository() -> None:
    repository = FakeScraperRepository()
    limiter = ScrapeConcurrencyLimiter(max_concurrent=2)
    service = ScrapeService(repository, limiter, scrape_timeout_seconds=5.0)
    params = ScrapeParams(stealth_mode=True, wait_until="networkidle")

    await service.scrape_url("https://example.com", params)

    assert repository.params_received == [params]


@pytest.mark.asyncio
async def test_scrape_url_defaults_params_to_none() -> None:
    repository = FakeScraperRepository()
    limiter = ScrapeConcurrencyLimiter(max_concurrent=2)
    service = ScrapeService(repository, limiter, scrape_timeout_seconds=5.0)

    await service.scrape_url("https://example.com")

    assert repository.params_received == [None]


@pytest.mark.asyncio
async def test_scrape_url_exposes_dedicated_browser_flag_in_metadata() -> None:
    repository = FakeScraperRepository(
        result=ScrapeResult(success=True, markdown="contenido", dedicated_browser=True)
    )
    limiter = ScrapeConcurrencyLimiter(max_concurrent=2)
    service = ScrapeService(repository, limiter, scrape_timeout_seconds=5.0)

    response = await service.scrape_url("https://example.com")

    assert response.metadata.dedicated_browser is True


@pytest.mark.asyncio
async def test_scrape_url_raises_scraper_error_when_unsuccessful() -> None:
    repository = FakeScraperRepository(
        result=ScrapeResult(success=False, error_message="Detectado bloqueo Akamai")
    )
    limiter = ScrapeConcurrencyLimiter(max_concurrent=2)
    service = ScrapeService(repository, limiter, scrape_timeout_seconds=5.0)

    with pytest.raises(ScrapeServiceError) as exc_info:
        await service.scrape_url("https://blocked.example.com")

    assert exc_info.value.code == ScrapeErrorCode.SCRAPER_ERROR
    assert "Akamai" in exc_info.value.message


@pytest.mark.asyncio
async def test_scrape_url_raises_timeout_error() -> None:
    repository = FakeScraperRepository(delay_seconds=0.2)
    limiter = ScrapeConcurrencyLimiter(max_concurrent=2)
    service = ScrapeService(repository, limiter, scrape_timeout_seconds=0.02)

    with pytest.raises(ScrapeServiceError) as exc_info:
        await service.scrape_url("https://slow.example.com")

    assert exc_info.value.code == ScrapeErrorCode.TIMEOUT


@pytest.mark.asyncio
async def test_scrape_url_raises_concurrency_limit_error() -> None:
    repository = FakeScraperRepository(delay_seconds=0.2)
    limiter = ScrapeConcurrencyLimiter(max_concurrent=1, acquire_timeout_seconds=0.05)
    service = ScrapeService(repository, limiter, scrape_timeout_seconds=5.0)

    async def occupy_slot() -> None:
        async with limiter.slot():
            await asyncio.sleep(0.3)

    holder = asyncio.create_task(occupy_slot())
    await asyncio.sleep(0.02)

    with pytest.raises(ScrapeServiceError) as exc_info:
        await service.scrape_url("https://another.example.com")

    assert exc_info.value.code == ScrapeErrorCode.CONCURRENCY_LIMIT_EXCEEDED
    await holder


@pytest.mark.asyncio
async def test_scrape_url_wraps_unexpected_repository_exception() -> None:
    repository = FakeScraperRepository(raise_exc=RuntimeError("El navegador ha crasheado"))
    limiter = ScrapeConcurrencyLimiter(max_concurrent=2)
    service = ScrapeService(repository, limiter, scrape_timeout_seconds=5.0)

    with pytest.raises(ScrapeServiceError) as exc_info:
        await service.scrape_url("https://crash.example.com")

    assert exc_info.value.code == ScrapeErrorCode.SCRAPER_ERROR
    assert "navegador ha crasheado" in exc_info.value.message
