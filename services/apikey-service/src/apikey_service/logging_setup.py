import logging
import sys

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


def setup_logging() -> None:
    logger.remove()
    logger.add(sys.stdout, level="INFO", enqueue=True)

    resource = Resource.create({"service.name": settings.otel_service_name})
    provider = LoggerProvider(resource=resource)
    provider.add_log_record_processor(
        BatchLogRecordProcessor(OTLPLogExporter(endpoint=settings.otel_exporter_otlp_logs_endpoint))
    )
    set_logger_provider(provider)

    audit_logger.setLevel(logging.WARNING)
    audit_logger.addHandler(LoggingHandler(logger_provider=provider))
    audit_logger.propagate = False
