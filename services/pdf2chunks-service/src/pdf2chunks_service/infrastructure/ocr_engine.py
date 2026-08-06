"""Envoltorio sobre el OCR integrado de PyMuPDF (Tesseract) — aísla la
dependencia externa del resto de capas."""

from __future__ import annotations

import fitz  # PyMuPDF

from pdf2chunks_service.domain.models import OcrError


def page_needs_ocr(native_text: str, char_threshold: int) -> bool:
    """True si el texto nativo tiene menos caracteres útiles que `char_threshold`."""
    return len(native_text.strip()) < char_threshold


def ocr_page(page: fitz.Page, language: str = "eng") -> str:
    """Aplica OCR (Tesseract, integrado en PyMuPDF) sobre una página.

    Raises:
        OcrError: si Tesseract no está disponible o el OCR falla.
    """
    try:
        textpage = page.get_textpage_ocr(flags=0, language=language, full=True)
        return page.get_text(textpage=textpage) or ""
    except Exception as exc:  # pragma: no cover - depende del entorno con tesseract
        raise OcrError(f"Fallo al aplicar OCR en la página: {exc}") from exc
