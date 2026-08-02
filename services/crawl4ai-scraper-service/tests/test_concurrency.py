"""Tests unitarios de ScrapeConcurrencyLimiter (semáforo de concurrencia)."""

from __future__ import annotations

import asyncio

import pytest

from crawl4ai_scraper_service.services.concurrency import (
    ConcurrencyLimitTimeoutError,
    ScrapeConcurrencyLimiter,
)


def test_invalid_max_concurrent_raises_value_error() -> None:
    with pytest.raises(ValueError):
        ScrapeConcurrencyLimiter(max_concurrent=0)


@pytest.mark.asyncio
async def test_slot_tracks_active_count() -> None:
    limiter = ScrapeConcurrencyLimiter(max_concurrent=2)
    assert limiter.active_count == 0

    async with limiter.slot():
        assert limiter.active_count == 1
        async with limiter.slot():
            assert limiter.active_count == 2

    assert limiter.active_count == 0


@pytest.mark.asyncio
async def test_slot_enforces_max_concurrent() -> None:
    limiter = ScrapeConcurrencyLimiter(max_concurrent=1, acquire_timeout_seconds=0.2)
    order: list[str] = []

    async def task(name: str, hold: float) -> None:
        async with limiter.slot():
            order.append(f"start:{name}")
            await asyncio.sleep(hold)
            order.append(f"end:{name}")

    await asyncio.gather(task("a", 0.05), task("b", 0.05))

    # No pueden solaparse: "a" debe terminar antes de que "b" empiece,
    # dado que max_concurrent=1.
    assert order == ["start:a", "end:a", "start:b", "end:b"]


@pytest.mark.asyncio
async def test_slot_raises_timeout_error_when_exhausted() -> None:
    limiter = ScrapeConcurrencyLimiter(max_concurrent=1, acquire_timeout_seconds=0.05)

    async def hold_slot() -> None:
        async with limiter.slot():
            await asyncio.sleep(0.3)

    holder = asyncio.create_task(hold_slot())
    await asyncio.sleep(0.02)

    with pytest.raises(ConcurrencyLimitTimeoutError):
        async with limiter.slot():
            pass  # pragma: no cover - no debería llegar aquí

    await holder


@pytest.mark.asyncio
async def test_slot_waits_indefinitely_when_timeout_is_zero() -> None:
    limiter = ScrapeConcurrencyLimiter(max_concurrent=1, acquire_timeout_seconds=0)

    async def hold_slot_briefly() -> None:
        async with limiter.slot():
            await asyncio.sleep(0.1)

    holder = asyncio.create_task(hold_slot_briefly())
    await asyncio.sleep(0.02)

    # No debe lanzar timeout: espera hasta que se libera el slot.
    async with limiter.slot():
        assert limiter.active_count == 1

    await holder
