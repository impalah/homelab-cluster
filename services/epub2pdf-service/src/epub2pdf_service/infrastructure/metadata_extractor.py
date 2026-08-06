"""Envoltorio sobre `ebooklib` — aísla la dependencia externa del resto de
capas (el service no importa `ebooklib` directamente)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ebooklib import epub

from epub2pdf_service.domain.models import EpubMetadata, EpubMetadataError


def _first_value(values: list[tuple[str, dict[str, Any]]]) -> str | None:
    if not values:
        return None
    value = values[0][0]
    return str(value) if value is not None else None


def extract_metadata(epub_path: Path) -> EpubMetadata:
    """Extrae los metadatos de un fichero EPUB.

    Raises:
        EpubMetadataError: si el fichero está corrupto o no se puede leer
            como EPUB válido.
    """
    try:
        book = epub.read_epub(str(epub_path), options={"ignore_ncx": True})
    except Exception as exc:  # ebooklib puede lanzar varias excepciones distintas
        raise EpubMetadataError(f"No se pudo leer el EPUB '{epub_path.name}': {exc}") from exc

    try:
        titles = book.get_metadata("DC", "title")
        creators = book.get_metadata("DC", "creator")
        dates = book.get_metadata("DC", "date")
        languages = book.get_metadata("DC", "language")
        publishers = book.get_metadata("DC", "publisher")
        identifiers = book.get_metadata("DC", "identifier")

        authors = [str(value) for value, _attrs in creators] if creators else []

        return EpubMetadata(
            title=_first_value(titles),
            authors=authors,
            date=_first_value(dates),
            language=_first_value(languages),
            publisher=_first_value(publishers),
            identifier=_first_value(identifiers),
            source_filename=epub_path.name,
        )
    except Exception as exc:
        raise EpubMetadataError(
            f"Error al procesar metadatos de '{epub_path.name}': {exc}"
        ) from exc


def write_metadata_sidecar(metadata: EpubMetadata, sidecar_path: Path) -> None:
    """Escribe los metadatos como JSON en la ruta indicada."""
    sidecar_path.write_text(
        json.dumps(metadata.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
