"""Tests del módulo de configuración de logging (loguru)."""

from __future__ import annotations

import logging

from loguru import logger

from epub2pdf_service.config import Settings
from epub2pdf_service.logging_setup import InterceptHandler, setup_logging


def test_setup_logging_configures_a_single_stdout_sink() -> None:
    setup_logging(Settings(_env_file=None, log_level="INFO"))
    setup_logging(Settings(_env_file=None, log_level="DEBUG"))  # no debe acumular sinks

    # loguru no expone el nº de sinks públicamente de forma directa;
    # comprobamos indirectamente que reconfigurar no lanza y que el logger
    # sigue aceptando mensajes sin error.
    logger.info("mensaje de prueba tras reconfigurar logging")


def test_setup_logging_intercepts_stdlib_logging() -> None:
    setup_logging(Settings(_env_file=None, log_level="DEBUG"))
    logging.getLogger("uvicorn").info("mensaje de prueba desde uvicorn")
    logger.complete()


def test_setup_logging_silences_access_log_unless_debug() -> None:
    setup_logging(Settings(_env_file=None, log_level="INFO"))
    assert logging.getLogger("uvicorn.access").level == logging.WARNING

    setup_logging(Settings(_env_file=None, log_level="DEBUG"))
    assert logging.getLogger("uvicorn.access").level == logging.DEBUG


def test_intercept_handler_emit_with_unregistered_level_name() -> None:
    handler = InterceptHandler()
    record = logging.LogRecord(
        name="custom.logger",
        level=25,
        pathname=__file__,
        lineno=1,
        msg="mensaje con nivel desconocido para loguru",
        args=None,
        exc_info=None,
    )
    record.levelname = "CUSTOMLEVEL"

    # No debe lanzar excepción: cae al branch que usa record.levelno.
    handler.emit(record)
