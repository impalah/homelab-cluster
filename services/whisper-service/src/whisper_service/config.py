"""Configuración de whisper-service vía variables de entorno."""

from typing import Literal

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    whisper_model: str = "large-v3"
    whisper_device: str = "cuda"
    whisper_compute_type: str = "float16"
    whisper_language: str = "es"
    host: str = "0.0.0.0"
    port: int = 9800
    log_level: str = "INFO"
    log_format: Literal["text", "json"] = "text"

    model_config = {"env_prefix": "", "case_sensitive": False}


settings = Settings()
