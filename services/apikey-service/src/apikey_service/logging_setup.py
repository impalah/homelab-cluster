from __future__ import annotations

import logging
import sys
from types import FrameType
from typing import cast

from loguru import logger
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.resources import Resource

from apikey_service.config import settings

# Logger de auditoría: intentos de acceso incorrectos (POST /keys con token de
# admin inválido, GET /validate con una API key inexistente o revocada).
# Va por un canal aparte del logging general (loguru -> stdout) porque su
# destino es el pipeline OTel -> Loki ya existente en el clúster
# (pi-obs/config/otel-collector.yaml, pipeline "logs"), no la consola del
# contenedor. Usa logging estándar porque el SDK de OTel para Python se
# integra con logging.Handler, no con los sinks de loguru.
audit_logger = logging.getLogger("apikey_service.audit")


class InterceptHandler(logging.Handler):
    """Handler de `logging` estándar que reenvía los registros a Loguru.

    Permite interceptar logs de librerías de terceros (uvicorn, fastapi,
    sqlalchemy, etc.) que usan el módulo `logging` de la librería estándar y
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
)


def setup_logging() -> None:
    """Configura Loguru (consola) + el canal OTel de auditoría (Loki)."""
    logger.remove()
    logger.add(
        sys.stdout,
        level=settings.log_level,
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

    resource = Resource.create({"service.name": settings.otel_service_name})
    provider = LoggerProvider(resource=resource)
    provider.add_log_record_processor(
        BatchLogRecordProcessor(OTLPLogExporter(endpoint=settings.otel_exporter_otlp_logs_endpoint))
    )
    set_logger_provider(provider)

    audit_logger.setLevel(logging.WARNING)
    audit_logger.addHandler(LoggingHandler(logger_provider=provider))
    audit_logger.propagate = False
