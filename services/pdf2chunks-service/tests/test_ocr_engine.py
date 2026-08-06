"""Tests para pdf2chunks_service.infrastructure.ocr_engine."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from pdf2chunks_service.domain.models import OcrError
from pdf2chunks_service.infrastructure.ocr_engine import ocr_page, page_needs_ocr


@pytest.mark.parametrize(
    "text,threshold,expected",
    [
        ("", 20, True),
        ("   ", 20, True),
        ("abc", 20, True),
        ("x" * 25, 20, False),
        ("x" * 20, 20, False),
        ("x" * 19, 20, True),
    ],
)
def test_page_needs_ocr(text, threshold, expected):
    assert page_needs_ocr(text, threshold) is expected


def test_ocr_page_success_returns_text():
    mock_page = MagicMock()
    mock_textpage = MagicMock()
    mock_page.get_textpage_ocr.return_value = mock_textpage
    mock_page.get_text.return_value = "texto reconocido por ocr"

    result = ocr_page(mock_page, language="eng")

    assert result == "texto reconocido por ocr"
    mock_page.get_textpage_ocr.assert_called_once()
    mock_page.get_text.assert_called_once_with(textpage=mock_textpage)


def test_ocr_page_empty_result():
    mock_page = MagicMock()
    mock_page.get_textpage_ocr.return_value = MagicMock()
    mock_page.get_text.return_value = ""

    result = ocr_page(mock_page)
    assert result == ""


def test_ocr_page_raises_ocr_error_on_failure():
    mock_page = MagicMock()
    mock_page.get_textpage_ocr.side_effect = RuntimeError("tesseract no encontrado")

    with pytest.raises(OcrError, match="Fallo al aplicar OCR"):
        ocr_page(mock_page)
