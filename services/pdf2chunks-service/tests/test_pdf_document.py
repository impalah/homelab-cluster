"""Tests para pdf2chunks_service.infrastructure.pdf_document."""

from __future__ import annotations

from pathlib import Path

import fitz
import pytest

from pdf2chunks_service.domain.models import PdfCorruptError, PdfEncryptedError
from pdf2chunks_service.infrastructure.pdf_document import (
    close_pdf,
    compute_document_id,
    extract_title_author,
    extract_toc,
    get_page_count,
    get_page_native_text,
    open_pdf,
)


def test_compute_document_id_is_deterministic(native_text_pdf: Path):
    id1 = compute_document_id(native_text_pdf)
    id2 = compute_document_id(native_text_pdf)
    assert id1 == id2
    assert len(id1) == 64  # sha256 hex digest length


def test_compute_document_id_differs_between_files(native_text_pdf: Path, blank_pdf: Path):
    assert compute_document_id(native_text_pdf) != compute_document_id(blank_pdf)


def test_open_pdf_valid(native_text_pdf: Path):
    doc = open_pdf(native_text_pdf)
    assert get_page_count(doc) == 3
    close_pdf(doc)


def test_open_pdf_corrupt_raises(corrupt_pdf: Path):
    with pytest.raises(PdfCorruptError):
        open_pdf(corrupt_pdf)


def test_open_pdf_encrypted_raises(encrypted_pdf: Path):
    with pytest.raises(PdfEncryptedError):
        open_pdf(encrypted_pdf)


def test_extract_toc_with_entries(native_text_pdf: Path):
    doc = fitz.open(native_text_pdf)
    toc = extract_toc(doc)
    doc.close()
    assert len(toc) == 3
    assert toc[0].title == "Introducción"
    assert toc[0].page == 1


def test_extract_toc_empty(native_text_pdf_no_toc: Path):
    doc = fitz.open(native_text_pdf_no_toc)
    toc = extract_toc(doc)
    doc.close()
    assert toc == []


def test_extract_title_author(native_text_pdf: Path):
    doc = fitz.open(native_text_pdf)
    title, author = extract_title_author(doc)
    doc.close()
    assert title == "Documento de Prueba"
    assert author == "Autor de Prueba"


def test_extract_title_author_missing_returns_none(blank_pdf: Path):
    doc = fitz.open(blank_pdf)
    title, author = extract_title_author(doc)
    doc.close()
    assert title is None
    assert author is None


def test_get_page_native_text_returns_page_and_text(native_text_pdf: Path):
    doc = fitz.open(native_text_pdf)
    page, text = get_page_native_text(doc, 0)
    doc.close()
    assert isinstance(page, fitz.Page)
    assert len(text) > 20


def test_get_page_native_text_blank_page_returns_empty(blank_pdf: Path):
    doc = fitz.open(blank_pdf)
    _, text = get_page_native_text(doc, 0)
    doc.close()
    assert text == ""
