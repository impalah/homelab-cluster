"""Modelos de dominio (Pydantic), independientes del framework de scraping.

Estos modelos representan el contrato de la API (request/response) y las
entidades internas que fluyen entre las capas de servicio y repositorio.
No dependen de Crawl4AI: la capa de infraestructura es responsable de
mapear sus propios resultados a estos modelos.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field


class ServiceStatus(StrEnum):
    """Estado general del servicio."""

    OK = "ok"
    DEGRADED = "degraded"
    ERROR = "error"


class ScrapeParams(BaseModel):
    """Overrides opcionales, por petición, sobre la configuración por defecto
    (`Settings`/`.env`). Cualquier campo omitido o en `null` usa el valor por
    defecto del despliegue — no hace falta enviar `params` en absoluto si no
    se necesita cambiar nada.

    `stealth_mode`/`undetected_browser` son configuración de **nivel
    navegador** (se fija al lanzar Chromium, no por petición individual) —
    cuando su valor efectivo difiere del configurado en el despliegue, la
    capa de repositorio lanza un navegador dedicado solo para esa petición
    en vez de reutilizar el navegador compartido (más lento, limitado por
    `MAX_CONCURRENT_DEDICATED_BROWSERS` para no agotar la RAM del nodo). El
    resto de campos son configuración de ejecución (`CrawlerRunConfig`),
    sin coste extra por variar en cada petición.

    `extra="forbid"`: un nombre de parámetro mal escrito da un 422 claro en
    vez de ignorarse en silencio.
    """

    model_config = ConfigDict(extra="forbid")

    stealth_mode: bool | None = Field(
        default=None,
        description="Nivel navegador — navegador dedicado si difiere del default del despliegue",
    )
    undetected_browser: bool | None = Field(
        default=None,
        description="Nivel navegador — navegador dedicado si difiere del default del despliegue",
    )
    magic_mode: bool | None = Field(default=None, description="Nivel ejecución, sin coste extra")
    wait_until: Literal["domcontentloaded", "load", "networkidle"] | None = Field(
        default=None, description="Nivel ejecución, sin coste extra"
    )
    page_timeout_ms: int | None = Field(
        default=None, gt=0, description="Nivel ejecución, sin coste extra"
    )
    word_count_threshold: int | None = Field(
        default=None, ge=0, description="Nivel ejecución, sin coste extra"
    )
    max_retries: int | None = Field(
        default=None, ge=0, description="Nivel ejecución, sin coste extra"
    )


class ScrapeRequest(BaseModel):
    """Cuerpo de la petición para `POST /scrape`."""

    url: AnyHttpUrl = Field(..., description="URL válida (http/https) a scrapear")
    params: ScrapeParams | None = Field(
        default=None,
        description="Overrides opcionales de configuración de scraping, solo para esta petición",
    )


class ScrapeMetadata(BaseModel):
    """Metadatos básicos devueltos junto al markdown resultante."""

    original_url: str = Field(..., description="URL original solicitada")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Instante (UTC) en el que se completó el scraping",
    )
    content_length: int = Field(..., ge=0, description="Longitud del markdown resultante")
    fallback_applied: bool = Field(
        default=False,
        description="True si se aplicó algún reintento/fallback para obtener el contenido",
    )
    attempts: int = Field(default=1, ge=1, description="Número de intentos realizados")
    resolved_by: str | None = Field(
        default=None,
        description="Estrategia que resolvió la petición: direct | proxy | fallback_fetch",
    )
    dedicated_browser: bool = Field(
        default=False,
        description=(
            "True si esta petición lanzó un navegador dedicado (por overrides "
            "de stealth_mode/undetected_browser en 'params') en vez de "
            "reutilizar el navegador compartido del servicio"
        ),
    )


class ScrapeResponse(BaseModel):
    """Respuesta de `POST /scrape`."""

    markdown: str = Field(..., description="Markdown limpio generado por Crawl4AI")
    metadata: ScrapeMetadata


class ScrapeResult(BaseModel):
    """Entidad interna: resultado crudo de un scrape, independiente de HTTP.

    Es el modelo que la capa de repositorio produce y que la capa de
    servicio consume/transforma. No conoce nada de FastAPI ni de Crawl4AI.
    """

    success: bool
    markdown: str = ""
    error_message: str | None = None
    fallback_applied: bool = False
    attempts: int = 1
    resolved_by: str | None = None
    dedicated_browser: bool = False


class HealthResponse(BaseModel):
    """Respuesta de `GET /health`."""

    status: ServiceStatus
    browser_ready: bool | None = Field(
        default=None,
        description="True si el navegador headless de Crawl4AI está inicializado",
    )
    active_scrapes: int = Field(default=0, ge=0)
    max_concurrent_scrapes: int = Field(default=0, ge=0)


class ScrapeErrorCode(StrEnum):
    """Códigos de error internos para mapear excepciones a respuestas HTTP."""

    TIMEOUT = "timeout"
    CONCURRENCY_LIMIT_EXCEEDED = "concurrency_limit_exceeded"
    SCRAPER_ERROR = "scraper_error"
    UNKNOWN = "unknown"


class ScrapeServiceError(Exception):
    """Error de dominio lanzado por la capa de servicio al fallar un scrape."""

    def __init__(self, code: ScrapeErrorCode, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)
