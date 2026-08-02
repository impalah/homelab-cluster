"""Gestión de concurrencia (backpressure) para las operaciones de scraping.

Encapsula un `asyncio.Semaphore` a nivel de aplicación que limita cuántos
scrapes se ejecutan simultáneamente. Las peticiones que exceden el límite
quedan en espera (no se rechazan), salvo que se agote un timeout de espera
configurable, en cuyo caso se lanza `ConcurrencyLimitTimeoutError`.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager


class ConcurrencyLimitTimeoutError(Exception):
    """Se lanza cuando una petición agota el timeout esperando un slot libre."""


class ScrapeConcurrencyLimiter:
    """Limita el número de scrapes concurrentes mediante un semáforo asyncio."""

    def __init__(self, max_concurrent: int, acquire_timeout_seconds: float = 0) -> None:
        if max_concurrent < 1:
            raise ValueError("max_concurrent debe ser >= 1")
        self._max_concurrent = max_concurrent
        self._acquire_timeout_seconds = acquire_timeout_seconds
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._active = 0

    @property
    def max_concurrent(self) -> int:
        return self._max_concurrent

    @property
    def active_count(self) -> int:
        """Número de scrapes actualmente en ejecución (slots ocupados)."""
        return self._active

    @asynccontextmanager
    async def slot(self) -> AsyncIterator[None]:
        """Context manager que adquiere un slot del semáforo con backpressure.

        Si `acquire_timeout_seconds` es 0 (o None), espera indefinidamente a
        que haya un slot libre. Si es mayor que 0 y se agota el tiempo de
        espera, lanza `ConcurrencyLimitTimeoutError` en lugar de bloquear
        para siempre.
        """
        acquired = await self._acquire()
        if not acquired:
            raise ConcurrencyLimitTimeoutError(
                f"No se obtuvo un slot de scraping tras "
                f"{self._acquire_timeout_seconds}s de espera "
                f"(máximo concurrente: {self._max_concurrent})"
            )
        try:
            self._active += 1
            yield
        finally:
            self._active -= 1
            self._semaphore.release()

    async def _acquire(self) -> bool:
        if not self._acquire_timeout_seconds:
            await self._semaphore.acquire()
            return True
        try:
            await asyncio.wait_for(self._semaphore.acquire(), timeout=self._acquire_timeout_seconds)
            return True
        except TimeoutError:
            return False
