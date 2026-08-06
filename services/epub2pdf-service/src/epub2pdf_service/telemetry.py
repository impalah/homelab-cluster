"""Instrumentación OpenTelemetry (trazas) para epub2pdf-service.

Expone un tracer y un context manager `traced_conversion` que crea un
span `epub_to_pdf.convert` con atributos relevantes (nombre de fichero,
tamaño, duración, resultado). Si no hay endpoint OTLP configurado, se usa
un TracerProvider por defecto que no exporta a ningún backend (no-op
efectivo), de modo que el servicio nunca falla por falta de configuración
de observabilidad — mismo criterio de "no-op sin endpoint" que el resto
de servicios del clúster con OTel opcional.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager

from loguru import logger
from opentelemetry import trace
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Span, Status, StatusCode

from epub2pdf_service.config import Settings

_tracer_provider_initialized = False


def init_telemetry(settings: Settings) -> None:
    """Inicializa el TracerProvider global de OpenTelemetry. Idempotente:
    llamadas repetidas no reinicializan nada."""
    global _tracer_provider_initialized
    if _tracer_provider_initialized:
        return

    resource = Resource.create({SERVICE_NAME: settings.otel_service_name})
    provider = TracerProvider(resource=resource)

    if settings.otel_enabled and settings.otel_exporter_otlp_endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                OTLPSpanExporter,
            )

            exporter = OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint)
            provider.add_span_processor(BatchSpanProcessor(exporter))
        except Exception:
            # Si el exportador no se puede inicializar (endpoint inválido,
            # dependencia ausente, etc.) degradamos a no-op sin romper el
            # arranque del servicio.
            logger.warning("No se pudo inicializar el exportador OTLP, modo no-op")

    trace.set_tracer_provider(provider)
    _tracer_provider_initialized = True


def get_tracer() -> trace.Tracer:
    return trace.get_tracer("epub2pdf-service")


@contextmanager
def traced_conversion(filename: str, file_size_bytes: int) -> Iterator[Span]:
    """Envuelve una conversión en un span `epub_to_pdf.convert` con los
    atributos `epub2pdf.filename`, `epub2pdf.file_size_bytes`,
    `epub2pdf.duration_seconds` y `epub2pdf.result` (success|failure)."""
    tracer = get_tracer()
    start = time.monotonic()
    with tracer.start_as_current_span("epub_to_pdf.convert") as span:
        span.set_attribute("epub2pdf.filename", filename)
        span.set_attribute("epub2pdf.file_size_bytes", file_size_bytes)
        try:
            yield span
            span.set_attribute("epub2pdf.result", "success")
            span.set_status(Status(StatusCode.OK))
        except Exception as exc:
            span.set_attribute("epub2pdf.result", "failure")
            span.set_attribute("epub2pdf.error_message", str(exc))
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            raise
        finally:
            span.set_attribute("epub2pdf.duration_seconds", time.monotonic() - start)
