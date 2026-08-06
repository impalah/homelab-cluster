"""Modelos de dominio puros — sin dependencias de FastAPI, PyMuPDF ni
Tesseract. Representan los conceptos del negocio (un documento, una
página, un chunk) independientemente de cómo se invoquen (CLI o API) o de
qué motor de extracción/OCR los produzca."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any


class PdfEncryptedError(Exception):
    """El PDF está encriptado/protegido y no se pudo autenticar."""


class PdfCorruptError(Exception):
    """El PDF está corrupto o no se pudo abrir/parsear."""


class OcrError(Exception):
    """Error al intentar aplicar OCR sobre una página."""


@dataclass
class TocEntry:
    """Entrada de la tabla de contenidos (TOC) de un PDF."""

    level: int
    title: str
    page: int  # página 1-indexada


@dataclass
class DocumentMetadata:
    """Metadatos de un documento PDF."""

    document_id: str
    source_file: str
    title: str | None = None
    author: str | None = None
    page_count: int = 0
    toc: list[TocEntry] = field(default_factory=list)

    def chapter_for_page(self, page: int) -> str | None:
        """Devuelve el título del capítulo/sección de la TOC que cubre `page`.

        El título de la entrada de TOC de mayor página <= `page`, o None si
        no hay TOC o no hay ninguna entrada aplicable.
        """
        if not self.toc:
            return None
        applicable = [entry for entry in self.toc if entry.page <= page]
        if not applicable:
            return None
        return max(applicable, key=lambda entry: entry.page).title


@dataclass
class PageContent:
    """Texto extraído de una página, junto con si requirió OCR."""

    page_number: int  # 1-indexada
    text: str
    ocr_applied: bool


@dataclass
class Chunk:
    """Un chunk de texto listo para ser indexado en un pipeline RAG."""

    chunk_id: str
    document_id: str
    text: str
    page: int
    chapter: str | None
    title: str | None
    author: str | None
    source_file: str
    chunk_index: int
    char_count: int
    ocr_applied: bool

    @classmethod
    def create(
        cls,
        *,
        document_id: str,
        text: str,
        page: int,
        chapter: str | None,
        title: str | None,
        author: str | None,
        source_file: str,
        chunk_index: int,
        ocr_applied: bool,
    ) -> Chunk:
        """Crea un Chunk generando automáticamente el `chunk_id` (UUID) y `char_count`."""
        return cls(
            chunk_id=str(uuid.uuid4()),
            document_id=document_id,
            text=text,
            page=page,
            chapter=chapter,
            title=title,
            author=author,
            source_file=source_file,
            chunk_index=chunk_index,
            char_count=len(text),
            ocr_applied=ocr_applied,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serializa el chunk a un diccionario plano compatible con JSON."""
        return {
            "chunk_id": self.chunk_id,
            "document_id": self.document_id,
            "text": self.text,
            "page": self.page,
            "chapter": self.chapter,
            "title": self.title,
            "author": self.author,
            "source_file": self.source_file,
            "chunk_index": self.chunk_index,
            "char_count": self.char_count,
            "ocr_applied": self.ocr_applied,
        }


@dataclass
class ProcessingResult:
    """Resultado del procesamiento de un único PDF."""

    source_file: str
    success: bool
    chunks: list[Chunk] = field(default_factory=list)
    error: str | None = None
    warnings: list[str] = field(default_factory=list)
