"""Tests unitarios de Crawl4AIRepository, mockeando `crawl4ai.AsyncWebCrawler`
por completo (sin red real ni navegador real)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from crawl4ai_scraper_service.core.config import Settings
from crawl4ai_scraper_service.domain.models import ScrapeParams
from crawl4ai_scraper_service.repositories.crawl4ai_repository import Crawl4AIRepository
from crawl4ai_scraper_service.services.concurrency import ConcurrencyLimitTimeoutError


class _FakeMarkdownObj:
    def __init__(self, raw: str, fit: str | None = None) -> None:
        self.raw_markdown = raw
        self.fit_markdown = fit


class _FakeAsyncWebCrawler:
    """Doble de `crawl4ai.AsyncWebCrawler` para tests."""

    instances: list[_FakeAsyncWebCrawler] = []

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.started = False
        self.closed = False
        self.next_result = SimpleNamespace(
            success=True,
            markdown="# Hola",
            error_message=None,
            crawl_stats={"attempts": 1, "resolved_by": "direct", "fallback_fetch_used": False},
        )
        _FakeAsyncWebCrawler.instances.append(self)

    async def start(self) -> None:
        self.started = True

    async def close(self) -> None:
        self.closed = True

    async def arun(self, url: str, config=None):  # noqa: ANN001
        self.last_url = url
        return self.next_result


@pytest.fixture(autouse=True)
def _reset_fake_instances():
    _FakeAsyncWebCrawler.instances.clear()
    yield
    _FakeAsyncWebCrawler.instances.clear()


@pytest.fixture
def patched_crawler(monkeypatch: pytest.MonkeyPatch) -> type[_FakeAsyncWebCrawler]:
    monkeypatch.setattr("crawl4ai.AsyncWebCrawler", _FakeAsyncWebCrawler)
    return _FakeAsyncWebCrawler


@pytest.mark.asyncio
async def test_start_initializes_crawler_once(patched_crawler) -> None:
    repo = Crawl4AIRepository(Settings(_env_file=None))

    await repo.start()
    await repo.start()  # segunda llamada no debe crear otra instancia

    assert len(patched_crawler.instances) == 1
    assert await repo.is_ready() is True


@pytest.mark.asyncio
async def test_start_passes_crawler_strategy_when_undetected_enabled(patched_crawler) -> None:
    settings = Settings(_env_file=None, enable_undetected_browser=True)
    repo = Crawl4AIRepository(settings)

    await repo.start()

    assert "crawler_strategy" in patched_crawler.instances[0].kwargs


@pytest.mark.asyncio
async def test_is_ready_false_before_start(patched_crawler) -> None:
    repo = Crawl4AIRepository(Settings(_env_file=None))
    assert await repo.is_ready() is False


@pytest.mark.asyncio
async def test_stop_closes_crawler_and_resets_state(patched_crawler) -> None:
    repo = Crawl4AIRepository(Settings(_env_file=None))
    await repo.start()

    await repo.stop()

    assert patched_crawler.instances[0].closed is True
    assert await repo.is_ready() is False

    # stop() de nuevo no debe fallar (no-op si ya está cerrado).
    await repo.stop()


@pytest.mark.asyncio
async def test_scrape_without_start_raises_runtime_error() -> None:
    repo = Crawl4AIRepository(Settings(_env_file=None))
    with pytest.raises(RuntimeError):
        await repo.scrape("https://example.com")


@pytest.mark.asyncio
async def test_scrape_success_maps_plain_string_markdown(patched_crawler) -> None:
    repo = Crawl4AIRepository(Settings(_env_file=None))
    await repo.start()
    patched_crawler.instances[0].next_result = SimpleNamespace(
        success=True,
        markdown="contenido plano",
        error_message=None,
        crawl_stats={"attempts": 1, "resolved_by": "direct", "fallback_fetch_used": False},
    )

    result = await repo.scrape("https://example.com")

    assert result.success is True
    assert result.markdown == "contenido plano"
    assert result.fallback_applied is False
    assert result.attempts == 1
    assert result.resolved_by == "direct"


@pytest.mark.asyncio
async def test_scrape_success_prefers_fit_markdown_object(patched_crawler) -> None:
    repo = Crawl4AIRepository(Settings(_env_file=None))
    await repo.start()
    patched_crawler.instances[0].next_result = SimpleNamespace(
        success=True,
        markdown=_FakeMarkdownObj(raw="raw version", fit="fit version"),
        error_message=None,
        crawl_stats={"attempts": 3, "resolved_by": "proxy", "fallback_fetch_used": False},
    )

    result = await repo.scrape("https://example.com")

    assert result.markdown == "fit version"
    assert result.fallback_applied is True  # attempts > 1
    assert result.attempts == 3
    assert result.resolved_by == "proxy"


@pytest.mark.asyncio
async def test_scrape_success_falls_back_to_raw_markdown_when_no_fit(patched_crawler) -> None:
    repo = Crawl4AIRepository(Settings(_env_file=None))
    await repo.start()
    patched_crawler.instances[0].next_result = SimpleNamespace(
        success=True,
        markdown=_FakeMarkdownObj(raw="solo raw", fit=None),
        error_message=None,
        crawl_stats={},
    )

    result = await repo.scrape("https://example.com")

    assert result.markdown == "solo raw"
    assert result.attempts == 1


@pytest.mark.asyncio
async def test_scrape_failure_maps_error_message(patched_crawler) -> None:
    repo = Crawl4AIRepository(Settings(_env_file=None))
    await repo.start()
    patched_crawler.instances[0].next_result = SimpleNamespace(
        success=False,
        markdown="",
        error_message="Bloqueo detectado (DataDome)",
        crawl_stats={"attempts": 3, "resolved_by": None, "fallback_fetch_used": True},
    )

    result = await repo.scrape("https://blocked.example.com")

    assert result.success is False
    assert result.error_message == "Bloqueo detectado (DataDome)"
    assert result.fallback_applied is True
    assert result.attempts == 3


@pytest.mark.asyncio
async def test_scrape_failure_default_error_message_when_missing(patched_crawler) -> None:
    repo = Crawl4AIRepository(Settings(_env_file=None))
    await repo.start()
    patched_crawler.instances[0].next_result = SimpleNamespace(
        success=False, markdown="", error_message=None, crawl_stats=None
    )

    result = await repo.scrape("https://blocked.example.com")

    assert result.success is False
    assert result.error_message == "Scraping falló"
    assert result.attempts == 1


# --- Overrides por petición (ScrapeParams) ---------------------------------


@pytest.mark.asyncio
async def test_scrape_without_params_reuses_shared_crawler(patched_crawler) -> None:
    repo = Crawl4AIRepository(Settings(_env_file=None))
    await repo.start()

    result = await repo.scrape("https://example.com", params=None)

    assert len(patched_crawler.instances) == 1  # ningún navegador dedicado
    assert result.dedicated_browser is False


@pytest.mark.asyncio
async def test_scrape_with_run_level_override_reuses_shared_crawler(patched_crawler) -> None:
    """wait_until/word_count_threshold/etc. son de nivel ejecución — sin navegador dedicado."""
    repo = Crawl4AIRepository(Settings(_env_file=None))
    await repo.start()
    params = ScrapeParams(wait_until="networkidle", word_count_threshold=5, max_retries=0)

    result = await repo.scrape("https://example.com", params=params)

    assert len(patched_crawler.instances) == 1
    assert result.dedicated_browser is False


@pytest.mark.asyncio
async def test_scrape_with_browser_override_matching_default_reuses_shared_crawler(
    patched_crawler,
) -> None:
    """Pedir explícitamente el mismo valor que ya está desplegado no debe lanzar nada nuevo."""
    settings = Settings(_env_file=None, enable_stealth_mode=False)
    repo = Crawl4AIRepository(settings)
    await repo.start()
    params = ScrapeParams(stealth_mode=False)

    result = await repo.scrape("https://example.com", params=params)

    assert len(patched_crawler.instances) == 1
    assert result.dedicated_browser is False


@pytest.mark.asyncio
async def test_scrape_with_differing_browser_override_launches_dedicated_crawler(
    patched_crawler,
) -> None:
    settings = Settings(_env_file=None, enable_stealth_mode=False)
    repo = Crawl4AIRepository(settings)
    await repo.start()
    shared = patched_crawler.instances[0]
    params = ScrapeParams(stealth_mode=True)

    result = await repo.scrape("https://example.com", params=params)

    assert len(patched_crawler.instances) == 2  # compartido + dedicado
    dedicated = patched_crawler.instances[1]
    assert dedicated.started is True
    assert dedicated.closed is True  # el dedicado se cierra tras usarse...
    assert shared.closed is False  # ...el compartido, no
    assert result.dedicated_browser is True


@pytest.mark.asyncio
async def test_scrape_with_differing_undetected_browser_override_launches_dedicated_crawler(
    patched_crawler,
) -> None:
    settings = Settings(_env_file=None, enable_undetected_browser=False)
    repo = Crawl4AIRepository(settings)
    await repo.start()
    params = ScrapeParams(undetected_browser=True)

    result = await repo.scrape("https://example.com", params=params)

    assert len(patched_crawler.instances) == 2
    assert "crawler_strategy" in patched_crawler.instances[1].kwargs
    assert result.dedicated_browser is True


@pytest.mark.asyncio
async def test_dedicated_browser_limiter_reads_max_concurrent_from_settings() -> None:
    settings = Settings(_env_file=None, max_concurrent_dedicated_browsers=3)
    repo = Crawl4AIRepository(settings)

    assert repo._dedicated_browser_limiter.max_concurrent == 3


@pytest.mark.asyncio
async def test_dedicated_browser_limiter_caps_concurrency(patched_crawler) -> None:
    """Con el límite de navegadores dedicados agotado, la siguiente petición
    que también necesite uno debe agotar el timeout de espera, sin afectar
    al navegador compartido."""
    settings = Settings(
        _env_file=None,
        enable_stealth_mode=False,
        max_concurrent_dedicated_browsers=1,
        semaphore_acquire_timeout_seconds=0.05,
    )
    repo = Crawl4AIRepository(settings)
    await repo.start()
    params = ScrapeParams(stealth_mode=True)

    async def occupy_slot() -> None:
        async with repo._dedicated_browser_limiter.slot():
            await asyncio.sleep(0.3)

    holder = asyncio.create_task(occupy_slot())
    await asyncio.sleep(0.02)

    with pytest.raises(ConcurrencyLimitTimeoutError):
        await repo.scrape("https://example.com", params=params)

    await holder
