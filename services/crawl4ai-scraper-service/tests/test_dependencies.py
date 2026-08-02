"""Tests unitarios de los proveedores de dependencias de FastAPI (Depends)."""

from __future__ import annotations

from types import SimpleNamespace

from crawl4ai_scraper_service.core.config import Settings
from crawl4ai_scraper_service.dependencies import (
    get_concurrency_limiter,
    get_health_service,
    get_scrape_service,
    get_scraper_repository,
)
from crawl4ai_scraper_service.services.concurrency import ScrapeConcurrencyLimiter
from crawl4ai_scraper_service.services.health_service import HealthService
from crawl4ai_scraper_service.services.scrape_service import ScrapeService
from tests.conftest import FakeScraperRepository


def _fake_request(repository, limiter) -> SimpleNamespace:
    state = SimpleNamespace(scraper_repository=repository, concurrency_limiter=limiter)
    app = SimpleNamespace(state=state)
    return SimpleNamespace(app=app)


def test_get_scraper_repository_reads_from_app_state() -> None:
    repository = FakeScraperRepository()
    limiter = ScrapeConcurrencyLimiter(max_concurrent=2)
    request = _fake_request(repository, limiter)

    assert get_scraper_repository(request) is repository


def test_get_concurrency_limiter_reads_from_app_state() -> None:
    repository = FakeScraperRepository()
    limiter = ScrapeConcurrencyLimiter(max_concurrent=2)
    request = _fake_request(repository, limiter)

    assert get_concurrency_limiter(request) is limiter


def test_get_scrape_service_injects_dependencies() -> None:
    repository = FakeScraperRepository()
    limiter = ScrapeConcurrencyLimiter(max_concurrent=2)
    settings = Settings(_env_file=None, scrape_timeout_seconds=30.0)

    service = get_scrape_service(repository=repository, limiter=limiter, settings=settings)

    assert isinstance(service, ScrapeService)
    assert service._repository is repository
    assert service._limiter is limiter
    assert service._scrape_timeout_seconds == 30.0


def test_get_health_service_injects_dependencies() -> None:
    repository = FakeScraperRepository()
    limiter = ScrapeConcurrencyLimiter(max_concurrent=2)

    service = get_health_service(repository=repository, limiter=limiter)

    assert isinstance(service, HealthService)
    assert service._repository is repository
    assert service._limiter is limiter
