"""Tests de la configuración de logging con Loguru."""

from __future__ import annotations

import logging

from loguru import logger

from crawl4ai_scraper_service.core.config import Settings
from crawl4ai_scraper_service.core.logging import InterceptHandler, configure_logging


def test_configure_logging_writes_to_file_and_intercepts_stdlib_logging(tmp_path) -> None:
    log_file = tmp_path / "app.log"
    settings = Settings(_env_file=None, log_file_path=str(log_file), log_level="DEBUG")

    configure_logging(settings)
    logging.getLogger("uvicorn").info("mensaje de prueba desde uvicorn")
    logger.complete()

    content = log_file.read_text()
    assert "mensaje de prueba desde uvicorn" in content


def test_configure_logging_json_format(tmp_path) -> None:
    log_file = tmp_path / "app.jsonl"
    settings = Settings(_env_file=None, log_file_path=str(log_file), log_format="json")

    configure_logging(settings)
    logger.info("evento en formato json")
    logger.complete()

    content = log_file.read_text()
    assert "evento en formato json" in content


def test_configure_logging_without_file_sink(tmp_path) -> None:
    settings = Settings(_env_file=None, log_file_path=None)
    # No debe lanzar excepción aunque no haya fichero de log configurado.
    configure_logging(settings)
    logger.info("solo consola")
    logger.complete()


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
