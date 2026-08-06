"""Fixtures compartidas para los tests de pdf2chunks-service."""

from __future__ import annotations

from pathlib import Path

import fitz
import pytest
from fastapi.testclient import TestClient

from pdf2chunks_service.main import app


def _make_native_text_pdf(path: Path, *, with_toc: bool = True, num_pages: int = 3) -> None:
    """Crea un PDF con texto nativo (no requiere OCR) usando PyMuPDF."""
    doc = fitz.open()
    lorem = (
        "Este es un párrafo de prueba con suficiente texto nativo para superar "
        "el umbral de caracteres configurado y evitar que se dispare el OCR. "
    ) * 20

    for i in range(num_pages):
        page = doc.new_page()
        page.insert_text((72, 72), f"Página {i + 1}\n\n{lorem}", fontsize=10)

    if with_toc:
        toc = [[1, "Introducción", 1]]
        if num_pages >= 2:
            toc.append([1, "Desarrollo", 2])
        if num_pages >= 3:
            toc.append([2, "Conclusión", 3])
        doc.set_toc(toc)

    doc.set_metadata({"title": "Documento de Prueba", "author": "Autor de Prueba"})
    doc.save(str(path))
    doc.close()


def _make_blank_pdf(path: Path, num_pages: int = 1) -> None:
    """Crea un PDF sin ningún texto (páginas en blanco), simulando necesidad de OCR."""
    doc = fitz.open()
    for _ in range(num_pages):
        doc.new_page()
    doc.save(str(path))
    doc.close()


def _make_encrypted_pdf(path: Path) -> None:
    """Crea un PDF protegido con contraseña de usuario."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Contenido secreto")
    doc.save(
        str(path),
        encryption=fitz.PDF_ENCRYPT_AES_256,
        user_pw="secret123",
        owner_pw="ownersecret",
    )
    doc.close()


def _make_corrupt_pdf(path: Path) -> None:
    """Crea un fichero .pdf inválido (no es un PDF real)."""
    path.write_bytes(b"esto no es un PDF valido %PDF-broken-content")


@pytest.fixture
def tmp_pdf_dir(tmp_path: Path) -> Path:
    """Carpeta temporal para colocar PDFs de entrada."""
    d = tmp_path / "input"
    d.mkdir()
    return d


@pytest.fixture
def output_dir(tmp_path: Path) -> Path:
    """Carpeta temporal de salida."""
    return tmp_path / "output"


@pytest.fixture
def native_text_pdf(tmp_pdf_dir: Path) -> Path:
    """PDF con texto nativo suficiente, con TOC de 3 entradas."""
    path = tmp_pdf_dir / "native.pdf"
    _make_native_text_pdf(path, with_toc=True, num_pages=3)
    return path


@pytest.fixture
def native_text_pdf_no_toc(tmp_pdf_dir: Path) -> Path:
    """PDF con texto nativo pero sin TOC."""
    path = tmp_pdf_dir / "native_no_toc.pdf"
    _make_native_text_pdf(path, with_toc=False, num_pages=2)
    return path


@pytest.fixture
def blank_pdf(tmp_pdf_dir: Path) -> Path:
    """PDF con páginas en blanco (sin texto en absoluto)."""
    path = tmp_pdf_dir / "blank.pdf"
    _make_blank_pdf(path, num_pages=1)
    return path


@pytest.fixture
def encrypted_pdf(tmp_pdf_dir: Path) -> Path:
    """PDF protegido con contraseña."""
    path = tmp_pdf_dir / "encrypted.pdf"
    _make_encrypted_pdf(path)
    return path


@pytest.fixture
def corrupt_pdf(tmp_pdf_dir: Path) -> Path:
    """Fichero .pdf corrupto/inválido."""
    path = tmp_pdf_dir / "corrupt.pdf"
    _make_corrupt_pdf(path)
    return path


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)
