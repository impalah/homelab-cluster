"""Configuración de pdf2chunks-service vía variables de entorno (prefijo
PDF2CHUNKS_), mismo patrón que apikey-service/markitdown-service/epub2pdf-service."""

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PDF2CHUNKS_")

    host: str = "0.0.0.0"
    port: int = 8004

    # Umbral de caracteres (tras strip) por debajo del cual una página se
    # considera "sin texto útil" y se le aplica OCR.
    ocr_char_threshold: int = 20
    # Idioma(s) para Tesseract OCR (códigos de 3 letras separados por "+"
    # para varios idiomas, p. ej. "eng+spa").
    ocr_language: str = "eng"

    # Tamaño objetivo de cada chunk, en tokens aproximados (palabras).
    chunk_size_tokens: int = 400
    # Ratio de solapamiento entre chunks consecutivos (0-1).
    chunk_overlap_ratio: float = 0.15
    # Solo "fixed_size" implementada; "recursive"/"semantic" reservadas.
    chunking_strategy: str = "fixed_size"
    # "json" (lista de chunks) o "jsonl" (un chunk por línea).
    output_format: str = "json"

    log_level: str = "INFO"
    log_format: Literal["text", "json"] = "text"


settings = Settings()
