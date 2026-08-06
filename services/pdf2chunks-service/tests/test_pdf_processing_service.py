"""Tests para pdf2chunks_service.services.pdf_processing_service."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from pdf2chunks_service.services.chunking_strategies import FixedSizeChunkingStrategy
from pdf2chunks_service.services.pdf_processing_service import (
    PdfProcessingService,
    discover_pdfs,
)

OCR_PAGE = "pdf2chunks_service.services.pdf_processing_service.ocr_engine.ocr_page"


def _service(ocr_char_threshold: int = 20, ocr_language: str = "eng") -> PdfProcessingService:
    return PdfProcessingService(
        ocr_char_threshold=ocr_char_threshold,
        ocr_language=ocr_language,
        chunking_strategy=FixedSizeChunkingStrategy(chunk_size_tokens=50, overlap_ratio=0.1),
    )


def test_discover_pdfs_single_file(native_text_pdf: Path):
    assert discover_pdfs(native_text_pdf) == [native_text_pdf]


def test_discover_pdfs_single_non_pdf_file(tmp_path: Path):
    f = tmp_path / "not_a_pdf.txt"
    f.write_text("hola")
    assert discover_pdfs(f) == []


def test_discover_pdfs_directory(tmp_pdf_dir: Path, native_text_pdf: Path, blank_pdf: Path):
    result = discover_pdfs(tmp_pdf_dir)
    assert set(result) == {native_text_pdf, blank_pdf}


def test_discover_pdfs_nonexistent_path(tmp_path: Path):
    assert discover_pdfs(tmp_path / "no_existe") == []


def test_process_native_text_success(native_text_pdf: Path):
    result = _service().process(native_text_pdf)

    assert result.success is True
    assert result.error is None
    assert len(result.chunks) > 0
    assert all(c.ocr_applied is False for c in result.chunks)
    assert all(c.title == "Documento de Prueba" for c in result.chunks)
    assert all(c.author == "Autor de Prueba" for c in result.chunks)
    # Página 1 debe mapear al capítulo "Introducción" según el TOC de prueba.
    page1_chunks = [c for c in result.chunks if c.page == 1]
    assert all(c.chapter == "Introducción" for c in page1_chunks)


def test_process_no_toc_chapter_is_none(native_text_pdf_no_toc: Path):
    result = _service().process(native_text_pdf_no_toc)
    assert result.success is True
    assert all(c.chapter is None for c in result.chunks)


def test_process_triggers_ocr_when_blank(blank_pdf: Path):
    with patch(OCR_PAGE, return_value="Texto largo obtenido por OCR " * 5) as mock_ocr:
        result = _service().process(blank_pdf)

    mock_ocr.assert_called_once()
    assert result.success is True
    assert len(result.chunks) > 0
    assert all(c.ocr_applied is True for c in result.chunks)


def test_process_ocr_fails_gracefully_warns(blank_pdf: Path):
    from pdf2chunks_service.domain.models import OcrError

    with patch(OCR_PAGE, side_effect=OcrError("tesseract no disponible")):
        result = _service().process(blank_pdf)

    assert result.success is True
    assert result.chunks == []
    assert any("fallo de ocr" in w.lower() for w in result.warnings)


def test_process_blank_page_no_text_after_ocr(blank_pdf: Path):
    with patch(OCR_PAGE, return_value=""):
        result = _service().process(blank_pdf)

    assert result.success is True
    assert result.chunks == []
    assert any("no se generó ningún chunk" in w.lower() for w in result.warnings)


def test_process_encrypted_returns_failure(encrypted_pdf: Path):
    result = _service().process(encrypted_pdf)
    assert result.success is False
    assert result.error is not None
    assert result.chunks == []


def test_process_corrupt_returns_failure(corrupt_pdf: Path):
    result = _service().process(corrupt_pdf)
    assert result.success is False
    assert result.error is not None


def test_process_unexpected_error_is_captured(native_text_pdf: Path):
    with patch(
        "pdf2chunks_service.services.pdf_processing_service.pdf_document.extract_toc",
        side_effect=RuntimeError("boom inesperado"),
    ):
        result = _service().process(native_text_pdf)
    assert result.success is False
    assert result.error is not None
    assert "boom inesperado" in result.error


def test_process_unreadable_file_returns_failure(tmp_path: Path):
    missing = tmp_path / "no_existe.pdf"
    result = _service().process(missing)
    assert result.success is False
    assert result.error is not None


def test_process_batch_empty_directory_returns_empty_list(tmp_pdf_dir: Path):
    assert _service().process_batch(tmp_pdf_dir) == []


def test_process_batch_mixed_results(tmp_pdf_dir: Path, native_text_pdf: Path, corrupt_pdf: Path):
    results = _service().process_batch(tmp_pdf_dir)
    statuses = {Path(r.source_file).name: r.success for r in results}
    assert statuses["native.pdf"] is True
    assert statuses["corrupt.pdf"] is False
