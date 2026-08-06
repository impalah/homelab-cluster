"""Configuración de markitdown-service vía variables de entorno."""

from typing import Literal

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    markitdown_port: int = 8001
    markitdown_log_level: str = "INFO"
    markitdown_log_format: Literal["text", "json"] = "text"
    host: str = "0.0.0.0"
    # Tamaño máximo de archivo aceptado (bytes): 50 MB por defecto
    max_file_size: int = 52_428_800

    model_config = {"env_prefix": "", "case_sensitive": False}


settings = Settings()
