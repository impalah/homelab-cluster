"""Fixtures compartidas para los tests de epub2pdf-service."""

from __future__ import annotations

from pathlib import Path

import pytest
from ebooklib import epub
from fastapi.testclient import TestClient

from epub2pdf_service.infrastructure.calibre_converter import CalibreConverter
from epub2pdf_service.main import app
from epub2pdf_service.services.conversion_service import ConversionService


def _build_epub(
    path: Path,
    title: str | None = "Libro de Prueba",
    author: str | None = "Autora de Prueba",
    language: str | None = "es",
    publisher: str | None = "Editorial Ficticia",
    date: str | None = "2024-01-01",
) -> None:
    book = epub.EpubBook()
    book.set_identifier("id-123456")
    if title is not None:
        book.set_title(title)
    if language is not None:
        book.set_language(language)
    if author is not None:
        book.add_author(author)
    if publisher is not None:
        book.add_metadata("DC", "publisher", publisher)
    if date is not None:
        book.add_metadata("DC", "date", date)

    chapter = epub.EpubHtml(title="Capitulo 1", file_name="chap_01.xhtml", lang=language or "en")
    chapter.content = "<h1>Capitulo 1</h1><p>Contenido de prueba.</p>"
    book.add_item(chapter)

    book.toc = (epub.Link("chap_01.xhtml", "Capitulo 1", "chap01"),)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", chapter]

    epub.write_epub(str(path), book)


# Alias público reutilizable desde otros módulos de test.
build_epub = _build_epub


@pytest.fixture()
def valid_epub_path(tmp_path: Path) -> Path:
    epub_file = tmp_path / "libro_valido.epub"
    _build_epub(epub_file)
    return epub_file


@pytest.fixture()
def epub_without_metadata_path(tmp_path: Path) -> Path:
    epub_file = tmp_path / "libro_sin_metadatos.epub"
    _build_epub(epub_file, title=None, author=None, publisher=None, date=None, language=None)
    return epub_file


@pytest.fixture()
def corrupt_epub_path(tmp_path: Path) -> Path:
    epub_file = tmp_path / "libro_corrupto.epub"
    epub_file.write_bytes(b"esto no es un zip valido ni un epub")
    return epub_file


@pytest.fixture()
def empty_input_dir(tmp_path: Path) -> Path:
    input_dir = tmp_path / "input_vacio"
    input_dir.mkdir()
    return input_dir


@pytest.fixture()
def output_dir(tmp_path: Path) -> Path:
    return tmp_path / "output"


@pytest.fixture()
def conversion_service() -> ConversionService:
    return ConversionService(
        CalibreConverter("ebook-convert"),
        conversion_timeout_seconds=5,
        max_filename_collision_attempts=10,
    )


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)
