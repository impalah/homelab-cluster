"""Configuración de logging centralizada con Loguru.

Sustituye completamente al módulo `logging` estándar: se instala un
`InterceptHandler` que redirige cualquier log emitido a través de
`logging` (por ejemplo, de Uvicorn, FastAPI o de librerías de terceros
como Playwright) hacia Loguru, de forma que todo el logging de la
aplicación pasa por un único sistema y formato consistente.
"""

from __future__ import annotations

import logging
import sys
from types import FrameType
from typing import cast

from loguru import logger

from crawl4ai_scraper_service.core.config import Settings


class InterceptHandler(logging.Handler):
    """Handler de `logging` estándar que reenvía los registros a Loguru.

    Permite interceptar logs de librerías de terceros (uvicorn, playwright,
    asyncio, etc.) que usan el módulo `logging` de la librería estándar y
    hacer que fluyan por Loguru con el mismo formato y sinks.
    """

    def emit(self, record: logging.LogRecord) -> None:  # noqa: D102
        level: int | str
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = cast(FrameType, frame.f_back)
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


# Nombres de loggers de terceros cuyo logging estándar queremos interceptar
# y redirigir hacia Loguru.
_THIRD_PARTY_LOGGERS: tuple[str, ...] = (
    "uvicorn",
    "uvicorn.access",
    "uvicorn.error",
    "fastapi",
    "asyncio",
    "playwright",
    "crawl4ai",
)


def configure_logging(settings: Settings) -> None:
    """Configura Loguru como único sistema de logging de la aplicación.

    - Elimina los sinks por defecto de Loguru y define uno para consola y,
      opcionalmente, otro para fichero (con rotación/retención).
    - Redirige el `logging` estándar (raíz + librerías conocidas) a Loguru
      mediante `InterceptHandler`, para que todo el output de logging de la
      aplicación (incluyendo terceros) sea consistente.
    """
    logger.remove()

    console_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
        "<level>{message}</level>"
    )

    logger.add(
        sys.stderr,
        level=settings.log_level,
        format=console_format,
        serialize=settings.log_format == "json",
        backtrace=settings.debug,
        diagnose=settings.debug,
        enqueue=True,
    )

    if settings.log_file_path:
        logger.add(
            settings.log_file_path,
            level=settings.log_level,
            rotation=settings.log_rotation,
            retention=settings.log_retention,
            serialize=settings.log_format == "json",
            enqueue=True,
        )

    # Redirige el logging estándar de la raíz a Loguru.
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)

    for logger_name in _THIRD_PARTY_LOGGERS:
        std_logger = logging.getLogger(logger_name)
        std_logger.handlers = [InterceptHandler()]
        std_logger.propagate = False

    # Los logs de acceso HTTP (una línea por petición, incluidos los
    # healthchecks de Docker cada pocos segundos) solo aportan valor en modo
    # depuración — a nivel normal, silenciar "uvicorn.access" evita inundar
    # Loki de líneas "GET /health 200" sin información útil.
    logging.getLogger("uvicorn.access").setLevel(
        logging.DEBUG if settings.log_level.upper() == "DEBUG" else logging.WARNING
    )

    logger.info(
        "Logging configurado (level={}, format={}, file={})",
        settings.log_level,
        settings.log_format,
        settings.log_file_path or "disabled",
    )
