"""Interfaz (Protocol) que abstrae la capa de infraestructura de scraping.

La capa de servicio depende únicamente de este `Protocol`, no de Crawl4AI
directamente. Esto permite sustituir el motor de scraping (por ejemplo,
otro proveedor, o un stub en tests) sin tocar la lógica de negocio.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from crawl4ai_scraper_service.domain.models import ScrapeParams, ScrapeResult


@runtime_checkable
class ScraperRepository(Protocol):
    """Contrato que debe cumplir cualquier adaptador de scraping."""

    async def start(self) -> None:
        """Inicializa recursos costosos (p.ej. lanzar el navegador)."""
        ...

    async def stop(self) -> None:
        """Libera recursos (p.ej. cerrar el navegador)."""
        ...

    async def is_ready(self) -> bool:
        """Indica si el motor de scraping está listo para recibir peticiones."""
        ...

    async def scrape(self, url: str, params: ScrapeParams | None = None) -> ScrapeResult:
        """Ejecuta el scraping de `url` y devuelve un `ScrapeResult` de dominio.

        `params`, si se indica, sobreescribe la configuración por defecto
        (`Settings`) solo para esta llamada — ver `ScrapeParams`.
        """
        ...
