"""Modelos de dominio puros — sin dependencias de FastAPI, subprocess ni
ebooklib. Representan los conceptos del negocio (una conversión, sus
metadatos) independientemente de cómo se invoquen (CLI o API) o de qué
motor de conversión los produzca."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class ConversionStatus(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"


class ConversionErrorReason(StrEnum):
    CORRUPT_EPUB = "corrupt_epub"
    TIMEOUT = "timeout"
    DRM_PROTECTED = "drm_protected"
    CALIBRE_FAILURE = "calibre_failure"
    METADATA_ERROR = "metadata_error"
    UNKNOWN = "unknown"


@dataclass
class ConversionResult:
    source_path: Path
    output_path: Path | None
    status: ConversionStatus
    reason: ConversionErrorReason | None = None
    message: str | None = None
    duration_seconds: float = 0.0


@dataclass
class EpubMetadata:
    """Metadatos relevantes extraídos de un fichero EPUB."""

    title: str | None = None
    authors: list[str] = field(default_factory=list)
    date: str | None = None
    language: str | None = None
    publisher: str | None = None
    identifier: str | None = None
    source_filename: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class EpubMetadataError(Exception):
    """Error al leer o parsear los metadatos de un EPUB."""
