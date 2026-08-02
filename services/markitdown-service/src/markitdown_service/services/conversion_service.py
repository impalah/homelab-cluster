"""Reglas de negocio de la conversión: validación de formato/tamaño, escritura
a fichero temporal, invocación del conversor y limpieza. No conoce FastAPI ni
HTTPException — eso lo traduce el controller a partir de las excepciones de
aquí (mismo patrón que apikey_service.services.apikey_service)."""

import contextlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from loguru import logger

from markitdown_service.infrastructure.document_converter import DocumentConverter

# Formatos soportados
SUPPORTED_EXTENSIONS = {
    ".pdf",
    ".docx",
    ".doc",
    ".xlsx",
    ".xls",
    ".pptx",
    ".ppt",
    ".html",
    ".htm",
    ".csv",
    ".json",
    ".xml",
    ".txt",
    ".md",
    ".rst",
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".bmp",
    ".webp",
    ".mp3",
    ".wav",
    ".ogg",
    ".m4a",
    ".zip",
}


class ConversionError(Exception):
    """Base de los errores de conversión — el controller la traduce a HTTPException."""


class UnsupportedFormatError(ConversionError):
    def __init__(self, extension: str) -> None:
        self.extension = extension
        super().__init__(f"Formato no soportado: '{extension}'")


class EmptyFileError(ConversionError):
    pass


class FileTooLargeError(ConversionError):
    def __init__(self, size_bytes: int, max_bytes: int) -> None:
        self.size_bytes = size_bytes
        self.max_bytes = max_bytes
        super().__init__(f"Archivo demasiado grande: {size_bytes} > {max_bytes} bytes")


class ConversionProducedNoContentError(ConversionError):
    pass


class ConversionFailedError(ConversionError):
    pass


@dataclass
class ConversionResult:
    filename: str
    extension: str
    size_bytes: int
    markdown: str
    characters: int


class ConversionService:
    def __init__(self, converter: DocumentConverter, max_file_size: int) -> None:
        self._converter = converter
        self._max_file_size = max_file_size

    def convert(self, content: bytes, original_name: str) -> ConversionResult:
        ext = Path(original_name).suffix.lower()

        if ext and ext not in SUPPORTED_EXTENSIONS:
            raise UnsupportedFormatError(ext)

        file_size = len(content)
        if file_size == 0:
            raise EmptyFileError()

        if file_size > self._max_file_size:
            raise FileTooLargeError(file_size, self._max_file_size)

        logger.info(
            "Convirtiendo: nombre={} tamaño={} bytes ext={}",
            original_name,
            file_size,
            ext or "desconocida",
        )

        tmp_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                tmp.write(content)
                tmp_path = tmp.name

            markdown_text = self._converter.convert(tmp_path)

            if not markdown_text or not markdown_text.strip():
                raise ConversionProducedNoContentError()

            logger.info("Conversión exitosa: {} caracteres generados.", len(markdown_text))

            return ConversionResult(
                filename=original_name,
                extension=ext or "desconocida",
                size_bytes=file_size,
                markdown=markdown_text,
                characters=len(markdown_text),
            )

        except ConversionError:
            raise
        except Exception as exc:
            logger.exception("Error al convertir '{}'", original_name)
            raise ConversionFailedError(str(exc)) from exc
        finally:
            if tmp_path is not None:
                with contextlib.suppress(Exception):
                    os.unlink(tmp_path)
