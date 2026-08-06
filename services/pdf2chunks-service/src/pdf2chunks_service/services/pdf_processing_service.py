"""Reglas de negocio de la extracción y troceado: descubrimiento de
ficheros, extracción de texto por página con fallback a OCR, orquestación
del chunking y manejo de errores por fichero individual. No conoce
FastAPI ni argparse — expone `ProcessingResult` (dominio), que el
controller o el CLI traducen a su formato de salida correspondiente.
Tampoco conoce PyMuPDF/Tesseract directamente — habla con
`infrastructure.pdf_document`/`infrastructure.ocr_engine` (mismo patrón
que `apikey_service.services.apikey_service`)."""

from __future__ import annotations

from pathlib import Path

import fitz  # PyMuPDF — solo para el type hint de fitz.Document, no se usa directamente aquí
from loguru import logger

from pdf2chunks_service.domain.models import (
    Chunk,
    DocumentMetadata,
    OcrError,
    PageContent,
    PdfCorruptError,
    PdfEncryptedError,
    ProcessingResult,
)
from pdf2chunks_service.infrastructure import ocr_engine, pdf_document
from pdf2chunks_service.services.chunking_strategies import ChunkingStrategy


def discover_pdfs(input_path: Path) -> list[Path]:
    """Resuelve la ruta de entrada a una lista de ficheros `.pdf` a procesar.

    Si `input_path` es un fichero, devuelve una lista con ese único
    fichero (si es `.pdf`). Si es una carpeta, devuelve todos los `.pdf`
    que contenga, ordenados por nombre. Vacía si no se encuentra nada.
    """
    if input_path.is_file():
        return [input_path] if input_path.suffix.lower() == ".pdf" else []
    if input_path.is_dir():
        return sorted(p for p in input_path.glob("*.pdf") if p.is_file())
    return []


class PdfProcessingService:
    """Orquesta la extracción de texto (nativo + OCR) y el troceado de un
    PDF. Recibe la estrategia de chunking y la configuración de OCR
    inyectadas por constructor, no las lee de `settings` directamente."""

    def __init__(
        self,
        ocr_char_threshold: int,
        ocr_language: str,
        chunking_strategy: ChunkingStrategy,
    ) -> None:
        self._ocr_char_threshold = ocr_char_threshold
        self._ocr_language = ocr_language
        self._chunking_strategy = chunking_strategy

    def _extract_page_content(
        self, doc: fitz.Document, page_index: int, warnings: list[str]
    ) -> PageContent:
        """Extrae el texto de una página, aplicando OCR si el texto nativo
        es insuficiente."""
        page, native_text = pdf_document.get_page_native_text(doc, page_index)
        page_number = page_index + 1

        if not ocr_engine.page_needs_ocr(native_text, self._ocr_char_threshold):
            return PageContent(page_number=page_number, text=native_text, ocr_applied=False)

        logger.info(
            "Texto nativo insuficiente en página {} ({} caracteres), aplicando OCR",
            page_number,
            len(native_text.strip()),
        )

        try:
            ocr_text = ocr_engine.ocr_page(page, language=self._ocr_language)
        except OcrError as exc:
            warnings.append(f"Página {page_number}: fallo de OCR ({exc}). Se usará texto nativo.")
            logger.warning("Fallo de OCR en página {}: {}", page_number, exc)
            return PageContent(page_number=page_number, text=native_text, ocr_applied=False)

        final_text = ocr_text if ocr_text.strip() else native_text
        ocr_applied = bool(ocr_text.strip())

        if not final_text.strip():
            warnings.append(
                f"Página {page_number}: no se pudo extraer texto ni con OCR "
                "(página posiblemente en blanco)."
            )
            logger.warning("Página {} sin texto tras OCR", page_number)

        return PageContent(page_number=page_number, text=final_text, ocr_applied=ocr_applied)

    def process(self, pdf_path: Path) -> ProcessingResult:
        """Procesa un único PDF: extrae texto (con OCR si hace falta) y
        genera chunks. Nunca lanza excepciones hacia el llamador: cualquier
        error se captura y se devuelve dentro de `ProcessingResult.error`,
        para que `process_batch` pueda continuar con el resto de ficheros.
        """
        warnings: list[str] = []

        try:
            document_id = pdf_document.compute_document_id(pdf_path)
        except OSError as exc:
            logger.error("No se pudo leer el fichero {}: {}", pdf_path, exc)
            return ProcessingResult(source_file=str(pdf_path), success=False, error=str(exc))

        doc = None
        try:
            doc = pdf_document.open_pdf(pdf_path)
            page_count = pdf_document.get_page_count(doc)
            title, author = pdf_document.extract_title_author(doc)
            toc = pdf_document.extract_toc(doc)

            metadata = DocumentMetadata(
                document_id=document_id,
                source_file=pdf_path.name,
                title=title,
                author=author,
                page_count=page_count,
                toc=toc,
            )

            if metadata.page_count == 0:
                warnings.append("El PDF no tiene páginas.")
                logger.warning("PDF sin páginas: {}", pdf_path.name)

            chunks: list[Chunk] = []
            chunk_index = 0

            for page_index in range(metadata.page_count):
                page_content = self._extract_page_content(doc, page_index, warnings)

                if not page_content.text.strip():
                    continue

                fragments = self._chunking_strategy.split(page_content.text)
                chapter = metadata.chapter_for_page(page_content.page_number)

                for fragment in fragments:
                    chunks.append(
                        Chunk.create(
                            document_id=document_id,
                            text=fragment,
                            page=page_content.page_number,
                            chapter=chapter,
                            title=metadata.title,
                            author=metadata.author,
                            source_file=pdf_path.name,
                            chunk_index=chunk_index,
                            ocr_applied=page_content.ocr_applied,
                        )
                    )
                    chunk_index += 1

            if not chunks:
                warnings.append("No se generó ningún chunk (documento sin texto extraíble).")
                logger.warning("PDF sin chunks generados: {}", pdf_path.name)

            return ProcessingResult(
                source_file=str(pdf_path), success=True, chunks=chunks, warnings=warnings
            )

        except PdfEncryptedError as exc:
            logger.error("PDF encriptado ({}): {}", pdf_path.name, exc)
            return ProcessingResult(source_file=str(pdf_path), success=False, error=str(exc))
        except PdfCorruptError as exc:
            logger.error("PDF corrupto ({}): {}", pdf_path.name, exc)
            return ProcessingResult(source_file=str(pdf_path), success=False, error=str(exc))
        except Exception as exc:  # salvaguarda final: nunca detener el lote
            logger.exception("Error inesperado procesando {}", pdf_path.name)
            return ProcessingResult(source_file=str(pdf_path), success=False, error=str(exc))
        finally:
            if doc is not None:
                pdf_document.close_pdf(doc)

    def process_batch(self, input_path: Path) -> list[ProcessingResult]:
        """Descubre y procesa todos los PDF encontrados en `input_path`."""
        pdf_files = discover_pdfs(input_path)

        if not pdf_files:
            logger.info("No se encontraron ficheros PDF en {}", input_path)
            return []

        return [self.process(pdf_path) for pdf_path in pdf_files]
