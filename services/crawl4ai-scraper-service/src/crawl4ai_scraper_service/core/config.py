"""Configuración centralizada de la aplicación con pydantic-settings.

Todas las variables de entorno de la aplicación se definen y validan aquí.
Se soporta un fichero `.env` en la raíz del proyecto para desarrollo local.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuración de la aplicación, resuelta desde variables de entorno / .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Aplicación ---------------------------------------------------
    app_name: str = Field(default="Crawl4AI Scraper Service")
    app_env: Literal["local", "staging", "production"] = Field(default="local")
    debug: bool = Field(default=False)
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)

    # --- Logging (Loguru) ----------------------------------------------
    log_level: str = Field(default="INFO")
    log_format: Literal["text", "json"] = Field(default="text")
    log_file_path: str | None = Field(default=None)
    log_rotation: str = Field(default="10 MB")
    log_retention: str = Field(default="7 days")

    # --- Concurrencia y timeouts ----------------------------------------
    max_concurrent_scrapes: int = Field(default=12, ge=1)
    scrape_timeout_seconds: float = Field(default=60.0, gt=0)
    semaphore_acquire_timeout_seconds: float = Field(default=90.0, ge=0)
    # Límite APARTE del anterior — solo para peticiones cuyo "params" pida
    # stealth_mode/undetected_browser distinto del default del despliegue
    # (lanzan un navegador Chromium dedicado, no el compartido). Valor bajo
    # a propósito: cada uno es un proceso Chromium completo, varios a la vez
    # pueden agotar la RAM en nodos pequeños (Raspberry Pi).
    max_concurrent_dedicated_browsers: int = Field(default=2, ge=1)

    # --- Crawl4AI: navegador --------------------------------------------
    crawler_headless: bool = Field(default=True)
    crawler_verbose: bool = Field(default=False)
    crawler_page_timeout_ms: int = Field(default=60000, gt=0)
    crawler_wait_until: Literal["domcontentloaded", "load", "networkidle"] = Field(
        default="domcontentloaded"
    )
    # Nº de páginas servidas por el navegador compartido antes de reciclarlo
    # (crear uno nuevo y drenar/cerrar el anterior). Sin esto, páginas que
    # Crawl4AI no logra cerrar tras un timeout/crash (falla silenciosa en su
    # propio cleanup interno) dejan procesos Chromium huérfanos que se van
    # acumulando indefinidamente en el navegador compartido de larga
    # duración — visto en producción: 39 procesos "--type=renderer" y 5GB de
    # RAM en un contenedor sin scrapes en curso. 0 = deshabilitado (default
    # de la librería, no usar).
    #
    # Bajado de 50 a 15 tras un segundo incidente en producción (2026-08-05):
    # con 50 el navegador acumuló 452MB -> 5,7GB en ~1h bajo una tanda con
    # muchos bloqueos anti-bot (cada reintento de MAX_RETRIES sobre una URL
    # bloqueada abre más páginas de las que este contador parece compensar
    # a tiempo) -- 50 páginas resultó ser un umbral demasiado alto para ese
    # patrón de carga real. 15 es más conservador: recicla más a menudo, a
    # cambio de una interrupción breve y barata en vez de agotar la RAM del
    # host entero.
    max_pages_before_recycle: int = Field(default=15, ge=0)

    # --- Anti-bot / anti-detección ---------------------------------------
    enable_stealth_mode: bool = Field(default=False)
    enable_undetected_browser: bool = Field(default=False)
    enable_magic_mode: bool = Field(default=False)

    enable_proxy: bool = Field(default=False)
    proxy_server: str | None = Field(default=None)
    proxy_username: str | None = Field(default=None)
    proxy_password: str | None = Field(default=None)

    max_retries: int = Field(default=2, ge=0)

    # --- Markdown ----------------------------------------------------------
    markdown_word_count_threshold: int = Field(default=10, ge=0)

    @field_validator("log_level")
    @classmethod
    def _normalize_log_level(cls, value: str) -> str:
        return value.upper()

    @property
    def proxy_configured(self) -> bool:
        """True si el proxy está activado y con servidor definido."""
        return self.enable_proxy and bool(self.proxy_server)


@lru_cache
def get_settings() -> Settings:
    """Devuelve una instancia cacheada (singleton) de Settings."""
    return Settings()
