"""Interfaz de línea de comandos para pdf2chunks-service.

Uso:
    python -m pdf2chunks_service.cli <input> <output> [opciones]

Pensada para invocarse como contenedor efímero por lote desde n8n
(Execute Command/SSH) — modo alternativo a la API HTTP persistente
(pdf2chunks_service.main), que es el modo por defecto de la imagen
Docker. Ambos modos comparten el mismo PdfProcessingService, así que el
comportamiento (extracción, OCR, chunking) es idéntico; el CLI añade la
posibilidad de sobrescribir la configuración de troceado por invocación
vía flags, cosa que la API no ofrece.

Códigos de salida (se preserva la convención del proyecto original
pdf2chunks, distinta de la de epub2pdf-service):
    0 -> Éxito total (todos los PDF se procesaron correctamente).
    1 -> Fallo total (todos fallaron, no había PDF que procesar, o la
         ruta de entrada no existe).
    2 -> Fallo parcial (al menos uno tuvo éxito y al menos uno falló).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from loguru import logger

from pdf2chunks_service.config import settings
from pdf2chunks_service.infrastructure import chunk_writer
from pdf2chunks_service.logging_setup import setup_logging
from pdf2chunks_service.services.chunking_strategies import get_chunking_strategy
from pdf2chunks_service.services.pdf_processing_service import PdfProcessingService

EXIT_SUCCESS = 0
EXIT_TOTAL_FAILURE = 1
EXIT_PARTIAL_FAILURE = 2


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pdf2chunks-service",
        description=(
            "Trocea ficheros PDF en fragmentos de texto para un pipeline RAG. "
            "Acepta un fichero .pdf individual o una carpeta con varios PDF "
            "(procesamiento por lote)."
        ),
    )
    parser.add_argument("input", type=str, help="Ruta de entrada: fichero .pdf o carpeta.")
    parser.add_argument("output", type=str, help="Carpeta de salida para los chunks generados.")
    parser.add_argument(
        "--ocr-char-threshold",
        type=int,
        default=None,
        help=f"Umbral de caracteres para activar OCR (por defecto {settings.ocr_char_threshold}).",
    )
    parser.add_argument(
        "--ocr-language",
        type=str,
        default=None,
        help=f"Idioma(s) para Tesseract OCR (por defecto {settings.ocr_language}).",
    )
    parser.add_argument(
        "--chunk-size-tokens",
        type=int,
        default=None,
        help=f"Tamaño de chunk en tokens aproximados (por defecto {settings.chunk_size_tokens}).",
    )
    parser.add_argument(
        "--chunk-overlap-ratio",
        type=float,
        default=None,
        help=f"Ratio de solapamiento entre chunks (por defecto {settings.chunk_overlap_ratio}).",
    )
    parser.add_argument(
        "--chunking-strategy",
        type=str,
        default=None,
        help=f"Estrategia de troceado (por defecto {settings.chunking_strategy}).",
    )
    parser.add_argument(
        "--output-format",
        type=str,
        choices=["json", "jsonl"],
        default=None,
        help=f"Formato de salida (por defecto {settings.output_format}).",
    )
    return parser


def run(argv: list[str] | None = None) -> int:
    setup_logging(settings)

    parser = build_arg_parser()
    args = parser.parse_args(argv)

    input_path = Path(args.input)
    output_path = Path(args.output)

    if not input_path.exists():
        logger.error("La ruta de entrada no existe: {}", input_path)
        return EXIT_TOTAL_FAILURE

    ocr_char_threshold = (
        args.ocr_char_threshold
        if args.ocr_char_threshold is not None
        else settings.ocr_char_threshold
    )
    ocr_language = args.ocr_language or settings.ocr_language
    chunk_size_tokens = (
        args.chunk_size_tokens if args.chunk_size_tokens is not None else settings.chunk_size_tokens
    )
    chunk_overlap_ratio = (
        args.chunk_overlap_ratio
        if args.chunk_overlap_ratio is not None
        else settings.chunk_overlap_ratio
    )
    chunking_strategy_name = args.chunking_strategy or settings.chunking_strategy
    output_format = args.output_format or settings.output_format

    service = PdfProcessingService(
        ocr_char_threshold=ocr_char_threshold,
        ocr_language=ocr_language,
        chunking_strategy=get_chunking_strategy(
            chunking_strategy_name,
            chunk_size_tokens=chunk_size_tokens,
            overlap_ratio=chunk_overlap_ratio,
        ),
    )

    logger.info("Iniciando procesamiento por lote: {} -> {}", input_path, output_path)

    results = service.process_batch(input_path)

    if not results:
        logger.error("No se procesó ningún fichero PDF en {}", input_path)
        return EXIT_TOTAL_FAILURE

    successes = [r for r in results if r.success]
    failures = [r for r in results if not r.success]

    for result in successes:
        chunk_writer.write_result(result, output_path, output_format)

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


def main() -> None:
    sys.exit(run())


if __name__ == "__main__":
    main()
