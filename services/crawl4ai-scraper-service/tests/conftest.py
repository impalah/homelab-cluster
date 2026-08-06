"""Fixtures compartidas para la suite de tests.

Construye una app de FastAPI de prueba que reutiliza los routers reales de
`crawl4ai_scraper_service.controllers`, pero con `app.dependency_overrides`
apuntando a dobles de test (repositorio y settings) en lugar del `lifespan`
real. Esto evita lanzar un navegador real de Crawl4AI durante los tests.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from crawl4ai_scraper_service.controllers.health_controller import router as health_router
from crawl4ai_scraper_service.controllers.scrape_controller import router as scrape_router
from crawl4ai_scraper_service.core.config import Settings, get_settings
from crawl4ai_scraper_service.dependencies import get_concurrency_limiter, get_scraper_repository
from crawl4ai_scraper_service.domain.models import ScrapeParams, ScrapeResult
from crawl4ai_scraper_service.services.concurrency import ScrapeConcurrencyLimiter

# `uv run` carga automáticamente el `.env` real del proyecto en el entorno
# del proceso (no solo pydantic-settings vía `env_file` — antes de que
# Python arranque siquiera). `Settings(_env_file=None)` desactiva solo la
# lectura del *fichero* .env por parte de pydantic-settings, no el propio
# `os.environ`, que ya viene contaminado por ese autoload de `uv run`. Sin
# esto, cualquier test que compruebe un valor *por defecto* de `Settings`
# depende de qué haya en el `.env` real de quien ejecute los tests — pasó de
# verdad: un `.env` local con `ENABLE_STEALTH_MODE=true`/`APP_ENV=production`
# (config de prueba manual, nada que ver con el código) hacía fallar
# `test_default_settings_values` y otros sin ningún cambio de código de por
# medio. Se limpian aquí, de forma autouse, todas las variables que
# `Settings` podría leer.
_SETTINGS_ENV_VARS = (
    "APP_NAME",
    "APP_ENV",
    "DEBUG",
    "HOST",
    "PORT",
    "LOG_LEVEL",
    "LOG_FORMAT",
    "LOG_FILE_PATH",
    "LOG_ROTATION",
    "LOG_RETENTION",
    "MAX_CONCURRENT_SCRAPES",
    "MAX_CONCURRENT_DEDICATED_BROWSERS",
    "SCRAPE_TIMEOUT_SECONDS",
    "SEMAPHORE_ACQUIRE_TIMEOUT_SECONDS",
    "CRAWLER_HEADLESS",
    "CRAWLER_VERBOSE",
    "CRAWLER_PAGE_TIMEOUT_MS",
    "CRAWLER_WAIT_UNTIL",
    "MAX_PAGES_BEFORE_RECYCLE",
    "ENABLE_STEALTH_MODE",
    "ENABLE_UNDETECTED_BROWSER",
    "ENABLE_MAGIC_MODE",
    "ENABLE_PROXY",
    "PROXY_SERVER",
    "PROXY_USERNAME",
    "PROXY_PASSWORD",
    "MAX_RETRIES",
    "MARKDOWN_WORD_COUNT_THRESHOLD",
)


@pytest.fixture(autouse=True)
def _clean_settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Aísla cada test de cualquier variable de entorno real ya presente.

    `monkeypatch.delenv` restaura el valor original (si lo había) al acabar
    el test, así que esto no afecta a nada fuera de la suite. También limpia
    la caché de `get_settings()` (`lru_cache`) para que ningún test vea una
    instancia de `Settings` construida antes con el entorno sin limpiar.
    """
    for var in _SETTINGS_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    get_settings.cache_clear()


@dataclass
class FakeScraperRepository:
    """Doble de test que implementa el `Protocol` `ScraperRepository`."""

    ready: bool = True
    result: ScrapeResult | None = None
    delay_seconds: float = 0.0
    raise_exc: Exception | None = None
    calls: list[str] = field(default_factory=list)
    params_received: list[ScrapeParams | None] = field(default_factory=list)
    started: bool = False

    def __post_init__(self) -> None:
        if self.result is None:
            self.result = ScrapeResult(
                success=True,
                markdown="# Título\n\nContenido de ejemplo limpio.",
                attempts=1,
                resolved_by="direct",
            )

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.started = False

    async def is_ready(self) -> bool:
        return self.ready

    async def scrape(self, url: str, params: ScrapeParams | None = None) -> ScrapeResult:
        self.calls.append(url)
        self.params_received.append(params)
        if self.delay_seconds:
            await asyncio.sleep(self.delay_seconds)
        if self.raise_exc:
            raise self.raise_exc
        assert self.result is not None
        return self.result


def build_test_app(
    repository: FakeScraperRepository,
    limiter: ScrapeConcurrencyLimiter,
    settings: Settings,
) -> FastAPI:
    """Crea una app FastAPI mínima con los routers reales y dependencias mockeadas."""
    app = FastAPI()
    app.include_router(health_router)
    app.include_router(scrape_router)
    app.dependency_overrides[get_scraper_repository] = lambda: repository
    app.dependency_overrides[get_concurrency_limiter] = lambda: limiter
    app.dependency_overrides[get_settings] = lambda: settings
    return app


@pytest.fixture
def test_settings() -> Settings:
    return Settings(scrape_timeout_seconds=5.0)


@pytest.fixture
def fake_repository() -> FakeScraperRepository:
    return FakeScraperRepository()


@pytest.fixture
def limiter() -> ScrapeConcurrencyLimiter:
    return ScrapeConcurrencyLimiter(max_concurrent=5, acquire_timeout_seconds=2.0)


@pytest.fixture
def client(
    fake_repository: FakeScraperRepository,
    limiter: ScrapeConcurrencyLimiter,
    test_settings: Settings,
) -> TestClient:
    app = build_test_app(fake_repository, limiter, test_settings)
    return TestClient(app)
