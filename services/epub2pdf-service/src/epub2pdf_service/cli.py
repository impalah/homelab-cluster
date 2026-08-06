"""Interfaz de línea de comandos para epub2pdf-service.

Uso:
    python -m epub2pdf_service.cli --input <ruta> --output <ruta>

Pensada para invocarse como contenedor efímero por lote desde n8n
(Execute Command/SSH) — modo alternativo a la API HTTP persistente
(epub2pdf_service.main), que es el modo por defecto de la imagen Docker.
Ambos modos comparten el mismo ConversionService, así que el
comportamiento (metadatos, colisiones de nombre, manejo de errores) es
idéntico.

Códigos de salida:
    0 -> Éxito total (todos los ficheros se convirtieron correctamente).
    1 -> Fallo parcial (al menos uno tuvo éxito y al menos uno falló).
    2 -> Fallo total (todos fallaron, no había ficheros que procesar, o
         la ruta de entrada no existe).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from loguru import logger

from epub2pdf_service.config import settings
from epub2pdf_service.dependencies import get_conversion_service
from epub2pdf_service.domain.models import ConversionStatus
from epub2pdf_service.logging_setup import setup_logging
from epub2pdf_service.telemetry import init_telemetry

EXIT_SUCCESS = 0
EXIT_PARTIAL_FAILURE = 1
EXIT_TOTAL_FAILURE = 2


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="epub2pdf-service",
        description=(
            "Convierte ficheros EPUB a PDF usando Calibre. Acepta un fichero "
            ".epub individual o una carpeta con varios EPUB (procesamiento por lote)."
        ),
    )
    parser.add_argument(
        "--input",
        "-i",
        dest="input_path",
        type=str,
        default=None,
        help="Ruta de entrada: fichero .epub o carpeta. Por defecto, EPUB2PDF_INPUT_PATH.",
    )
    parser.add_argument(
        "--output",
        "-o",
        dest="output_path",
        type=str,
        default=None,
        help="Carpeta de salida. Por defecto, EPUB2PDF_OUTPUT_PATH.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    setup_logging(settings)
    init_telemetry(settings)

    parser = build_arg_parser()
    args = parser.parse_args(argv)

    input_path = Path(args.input_path or settings.input_path)
    output_path = Path(args.output_path or settings.output_path)

    if not input_path.exists():
        logger.error("La ruta de entrada no existe: {}", input_path)
        return EXIT_TOTAL_FAILURE

    logger.info("Iniciando procesamiento por lote: {} -> {}", input_path, output_path)

    service = get_conversion_service()
    results = service.convert_batch(input_path, output_path)

    if not results:
        logger.error("No se procesó ningún fichero EPUB en {}", input_path)
        return EXIT_TOTAL_FAILURE

    successes = [r for r in results if r.status == ConversionStatus.SUCCESS]
    failures = [r for r in results if r.status == ConversionStatus.FAILURE]

    logger.info(
        "Lote finalizado: {} total, {} éxitos, {} fallos",
        len(results),
        len(successes),
        len(failures),
    )

    if failures and not successes:
        return EXIT_TOTAL_FAILURE
    if failures and successes:
        return EXIT_PARTIAL_FAILURE
    return EXIT_SUCCESS


if __name__ == "__main__":
    sys.exit(main())
