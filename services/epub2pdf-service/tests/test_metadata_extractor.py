"""Tests unitarios del envoltorio de extracción de metadatos (ebooklib)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from epub2pdf_service.domain.models import EpubMetadata, EpubMetadataError
from epub2pdf_service.infrastructure.metadata_extractor import (
    extract_metadata,
    write_metadata_sidecar,
)


def test_extract_metadata_valid_epub(valid_epub_path: Path) -> None:
    metadata = extract_metadata(valid_epub_path)

    assert metadata.title == "Libro de Prueba"
    assert metadata.authors == ["Autora de Prueba"]
    assert metadata.language == "es"
    assert metadata.publisher == "Editorial Ficticia"
    assert metadata.date == "2024-01-01"
    assert metadata.source_filename == "libro_valido.epub"


def test_extract_metadata_without_optional_fields(epub_without_metadata_path: Path) -> None:
    metadata = extract_metadata(epub_without_metadata_path)

    assert metadata.authors == []
    assert metadata.publisher is None
    assert metadata.date is None
    assert metadata.source_filename == "libro_sin_metadatos.epub"


def test_extract_metadata_corrupt_epub_raises(corrupt_epub_path: Path) -> None:
    with pytest.raises(EpubMetadataError):
        extract_metadata(corrupt_epub_path)


def test_extract_metadata_missing_file_raises(tmp_path: Path) -> None:
    missing = tmp_path / "no_existe.epub"
    with pytest.raises(EpubMetadataError):
        extract_metadata(missing)


def test_write_metadata_sidecar_creates_valid_json(tmp_path: Path) -> None:
    metadata = EpubMetadata(
        title="T",
        authors=["A"],
        date="2020",
        language="en",
        publisher="Pub",
        identifier="id-1",
        source_filename="t.epub",
    )
    sidecar = tmp_path / "t.meta.json"

    write_metadata_sidecar(metadata, sidecar)

    assert sidecar.exists()
    data = json.loads(sidecar.read_text(encoding="utf-8"))
    assert data["title"] == "T"
    assert data["authors"] == ["A"]
    assert data["publisher"] == "Pub"


def test_metadata_to_dict_roundtrip() -> None:
    metadata = EpubMetadata(title="X")
    d = metadata.to_dict()
    assert d["title"] == "X"
    assert d["authors"] == []
