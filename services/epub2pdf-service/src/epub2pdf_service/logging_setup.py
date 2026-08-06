"""Configuración de logging centralizada con Loguru.

Sustituye completamente al módulo `logging` estándar: se instala un
`InterceptHandler` que redirige cualquier log emitido a través de
`logging` (por ejemplo, de Uvicorn o FastAPI) hacia Loguru, de forma que
todo el logging de la aplicación pasa por un único sistema y formato
consistente. Compartida entre `main.py` (modo API) y `cli.py` (modo CLI,
invocado como contenedor efímero desde n8n), que configuran el sink cada
uno al arrancar.
"""

from __future__ import annotations

import logging
import sys
from types import FrameType
from typing import cast

from loguru import logger

from epub2pdf_service.config import Settings


class InterceptHandler(logging.Handler):
    """Handler de `logging` estándar que reenvía los registros a Loguru."""

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


_THIRD_PARTY_LOGGERS: tuple[str, ...] = (
    "uvicorn",
    "uvicorn.access",
    "uvicorn.error",
    "fastapi",
    "asyncio",
)


def setup_logging(settings: Settings) -> None:
    """Configura Loguru como único sistema de logging de la aplicación."""
    logger.remove()
    logger.add(
        sys.stdout,
        level=settings.log_level,
        serialize=settings.log_format == "json",
        enqueue=True,
    )

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
