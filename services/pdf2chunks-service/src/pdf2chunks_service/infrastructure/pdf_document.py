"""Envoltorio sobre PyMuPDF (`fitz`) — aísla la dependencia externa del
resto de capas. Es el único módulo que importa `fitz` para abrir/leer
documentos (`infrastructure/ocr_engine.py` es el único que lo usa para
OCR)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import fitz  # PyMuPDF

from pdf2chunks_service.domain.models import PdfCorruptError, PdfEncryptedError, TocEntry


def compute_document_id(pdf_path: Path) -> str:
    """Hash SHA-256 del contenido binario del PDF — mismo valor para todos
    los chunks de un mismo documento."""
    sha256 = hashlib.sha256()
    with pdf_path.open("rb") as fh:
        for block in iter(lambda: fh.read(65536), b""):
            sha256.update(block)
    return sha256.hexdigest()


def open_pdf(pdf_path: Path) -> fitz.Document:
    """Abre un PDF con PyMuPDF, traduciendo errores conocidos a excepciones
    de dominio.

    Raises:
        PdfCorruptError: si el fichero no se puede abrir o parsear.
        PdfEncryptedError: si el PDF está encriptado y no se puede desbloquear.
    """
    try:
        doc = fitz.open(pdf_path)
    except Exception as exc:
        raise PdfCorruptError(f"No se pudo abrir el PDF '{pdf_path.name}': {exc}") from exc

    # Intentar desbloquear con contraseña vacía (caso común de "protegido" sin password real).
    if doc.is_encrypted and not doc.authenticate(""):
        doc.close()
        raise PdfEncryptedError(
            f"El PDF '{pdf_path.name}' está encriptado/protegido y no se pudo autenticar"
        )

    return doc


def close_pdf(doc: fitz.Document) -> None:
    doc.close()


def get_page_count(doc: fitz.Document) -> int:
    return int(doc.page_count)


def extract_toc(doc: fitz.Document) -> list[TocEntry]:
    """Extrae la tabla de contenidos (TOC). Vacía si el PDF no tiene TOC."""
    raw_toc = doc.get_toc()  # lista de [level, title, page]
    return [TocEntry(level=level, title=title, page=page) for level, title, page in raw_toc]


def extract_title_author(doc: fitz.Document) -> tuple[str | None, str | None]:
    raw_meta = doc.metadata or {}
    title = raw_meta.get("title") or None
    author = raw_meta.get("author") or None
    return title, author


def get_page_native_text(doc: fitz.Document, page_index: int) -> tuple[fitz.Page, str]:
    """Devuelve la página (para poder pasarla a `ocr_engine.ocr_page` si
    hace falta) y su texto nativo (sin OCR)."""
    page = doc[page_index]
    return page, page.get_text() or ""
