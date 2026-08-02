"""Tests del ciclo de vida (lifespan) de la aplicación FastAPI."""

from __future__ import annotations

import pytest
from fastapi import FastAPI

from crawl4ai_scraper_service.core.lifespan import lifespan


class _FakeAsyncWebCrawler:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs

    async def start(self) -> None:
        pass

    async def close(self) -> None:
        pass

    async def arun(self, url: str, config=None):  # noqa: ANN001
        raise NotImplementedError


@pytest.mark.asyncio
async def test_lifespan_initializes_and_tears_down_app_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("crawl4ai.AsyncWebCrawler", _FakeAsyncWebCrawler)
    app = FastAPI()

    async with lifespan(app):
        assert app.state.scraper_repository is not None
        assert app.state.concurrency_limiter is not None
        assert await app.state.scraper_repository.is_ready() is True
        assert app.state.settings is not None

    assert await app.state.scraper_repository.is_ready() is False
