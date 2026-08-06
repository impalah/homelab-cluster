"""Configuración de epub2pdf-service vía variables de entorno (prefijo
EPUB2PDF_), mismo patrón que apikey-service/markitdown-service."""

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="EPUB2PDF_")

    host: str = "0.0.0.0"
    port: int = 8003

    # Rutas por defecto usadas por el CLI cuando no se pasan --input/--output
    # explícitos. La API no las usa como defecto: input_path/output_path
    # llegan siempre en el cuerpo de la petición POST /convert.
    input_path: str = "/data/input"
    output_path: str = "/data/output"

    calibre_binary: str = "ebook-convert"
    conversion_timeout_seconds: int = 300
    max_filename_collision_attempts: int = 1000
    log_level: str = "INFO"
    log_format: Literal["text", "json"] = "text"

    # Instrumentación OpenTelemetry (trazas, no logs) — si no hay endpoint
    # configurado, el servicio sigue funcionando en modo no-op: genera los
    # spans pero no los exporta a ningún backend.
    otel_enabled: bool = True
    otel_exporter_otlp_endpoint: str | None = None
    otel_service_name: str = "epub2pdf-service"


settings = Settings()
