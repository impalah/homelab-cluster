"""Reglas de negocio de la conversión EPUB -> PDF: descubrimiento de
ficheros, resolución de colisiones de nombre, orquestación de metadatos +
conversión, y manejo de errores por fichero individual. No conoce FastAPI
ni argparse — esos los traducen controllers/convert_controller.py y cli.py
a partir de las excepciones y resultados de aquí (mismo patrón que
apikey_service.services.apikey_service)."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

from loguru import logger

from epub2pdf_service.domain.models import (
    ConversionErrorReason,
    ConversionResult,
    ConversionStatus,
    EpubMetadataError,
)
from epub2pdf_service.infrastructure.calibre_converter import CalibreConverter, is_drm_error
from epub2pdf_service.infrastructure.metadata_extractor import (
    extract_metadata,
    write_metadata_sidecar,
)
from epub2pdf_service.telemetry import traced_conversion


def resolve_output_path(source_epub: Path, output_dir: Path, max_attempts: int = 1000) -> Path:
    """Calcula la ruta de salida del PDF evitando colisiones de nombre.

    Si `<stem>.pdf` ya existe, prueba `<stem> (1).pdf`, `<stem> (2).pdf`,
    etc., hasta encontrar un nombre libre.
    """
    base_name = source_epub.stem
    candidate = output_dir / f"{base_name}.pdf"
    if not candidate.exists():
        return candidate

    for attempt in range(1, max_attempts + 1):
        candidate = output_dir / f"{base_name} ({attempt}).pdf"
        if not candidate.exists():
            return candidate

    raise RuntimeError(
        f"No se pudo resolver un nombre de salida libre para '{source_epub.name}' "
        f"tras {max_attempts} intentos."
    )


def _sidecar_path_for(pdf_path: Path) -> Path:
    return pdf_path.parent / f"{pdf_path.stem}.meta.json"


def discover_epub_files(input_path: Path) -> list[Path]:
    """Devuelve la lista de ficheros .epub a procesar.

    Si `input_path` es un fichero, devuelve una lista con ese único fichero
    (si tiene extensión .epub). Si es una carpeta, devuelve todos los .epub
    que contenga (no recursivo), ordenados por nombre.
    """
    if input_path.is_file():
        if input_path.suffix.lower() == ".epub":
            return [input_path]
        return []

    if input_path.is_dir():
        return sorted(
            p for p in input_path.iterdir() if p.is_file() and p.suffix.lower() == ".epub"
        )

    return []


class ConversionService:
    """Orquesta la conversión: metadatos + Calibre + resolución de nombres.
    Recibe el conversor de Calibre inyectado (no lo instancia él mismo),
    mismo patrón que ConversionService de markitdown-service."""

    def __init__(
        self,
        converter: CalibreConverter,
        conversion_timeout_seconds: int,
        max_filename_collision_attempts: int,
    ) -> None:
        self._converter = converter
        self._timeout_seconds = conversion_timeout_seconds
        self._max_filename_collision_attempts = max_filename_collision_attempts

    def convert_single(self, source_epub: Path, output_dir: Path) -> ConversionResult:
        """Convierte un único EPUB a PDF y escribe el sidecar de metadatos.

        Nunca lanza excepciones hacia el llamador: todos los errores se
        capturan y se devuelven como parte de ConversionResult, para que
        `convert_batch` pueda continuar con el resto de ficheros.
        """
        start = time.monotonic()
        file_size = source_epub.stat().st_size if source_epub.exists() else 0

        try:
            with traced_conversion(source_epub.name, file_size):
                output_dir.mkdir(parents=True, exist_ok=True)

                try:
                    metadata = extract_metadata(source_epub)
                except EpubMetadataError as exc:
                    logger.error(
                        "No se pudieron extraer metadatos de {}, probablemente corrupto: {}",
                        source_epub.name,
                        exc,
                    )
                    return ConversionResult(
                        source_path=source_epub,
                        output_path=None,
                        status=ConversionStatus.FAILURE,
                        reason=ConversionErrorReason.CORRUPT_EPUB,
                        message=str(exc),
                        duration_seconds=time.monotonic() - start,
                    )

                output_pdf = resolve_output_path(
                    source_epub, output_dir, self._max_filename_collision_attempts
                )

                try:
                    proc = self._converter.convert(source_epub, output_pdf, self._timeout_seconds)
                except subprocess.TimeoutExpired as exc:
                    logger.error(
                        "Timeout convirtiendo {} (límite {}s)",
                        source_epub.name,
                        self._timeout_seconds,
                    )
                    return ConversionResult(
                        source_path=source_epub,
                        output_path=None,
                        status=ConversionStatus.FAILURE,
                        reason=ConversionErrorReason.TIMEOUT,
                        message=str(exc),
                        duration_seconds=time.monotonic() - start,
                    )

                if proc.returncode != 0:
                    stderr_text = proc.stderr or ""
                    reason = (
                        ConversionErrorReason.DRM_PROTECTED
                        if is_drm_error(stderr_text)
                        else ConversionErrorReason.CALIBRE_FAILURE
                    )
                    logger.error(
                        "Calibre falló al convertir {} (reason={}): {}",
                        source_epub.name,
                        reason.value,
                        stderr_text[:2000],
                    )
                    return ConversionResult(
                        source_path=source_epub,
                        output_path=None,
                        status=ConversionStatus.FAILURE,
                        reason=reason,
                        message=stderr_text.strip() or "Calibre devolvió un código de error",
                        duration_seconds=time.monotonic() - start,
                    )

                write_metadata_sidecar(metadata, _sidecar_path_for(output_pdf))

                duration = time.monotonic() - start
                logger.info(
                    "Conversión completada: {} -> {} ({:.2f}s)",
                    source_epub.name,
                    output_pdf.name,
                    duration,
                )
                return ConversionResult(
                    source_path=source_epub,
                    output_path=output_pdf,
                    status=ConversionStatus.SUCCESS,
                    duration_seconds=duration,
                )
        except Exception as exc:  # salvaguarda final: nunca detener el lote
            logger.exception("Error inesperado convirtiendo {}", source_epub.name)
            return ConversionResult(
                source_path=source_epub,
                output_path=None,
                status=ConversionStatus.FAILURE,
                reason=ConversionErrorReason.UNKNOWN,
                message=str(exc),
                duration_seconds=time.monotonic() - start,
            )

    def convert_batch(self, input_path: Path, output_dir: Path) -> list[ConversionResult]:
        """Procesa por lote todos los EPUB encontrados en `input_path`."""
        epub_files = discover_epub_files(input_path)

        if not epub_files:
            logger.info("No se encontraron ficheros EPUB en {}", input_path)
            return []

        return [self.convert_single(epub_file, output_dir) for epub_file in epub_files]
