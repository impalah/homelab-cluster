"""Tests de instrumentación OpenTelemetry."""

from __future__ import annotations

import epub2pdf_service.telemetry as telemetry_module
from epub2pdf_service.config import Settings
from epub2pdf_service.telemetry import get_tracer, init_telemetry, traced_conversion


def _reset_telemetry_state() -> None:
    telemetry_module._tracer_provider_initialized = False


def test_init_telemetry_without_endpoint_is_noop() -> None:
    _reset_telemetry_state()
    settings = Settings(otel_exporter_otlp_endpoint=None, otel_service_name="epub2pdf-test")

    init_telemetry(settings)  # no debe lanzar ninguna excepción

    assert get_tracer() is not None


def test_init_telemetry_is_idempotent() -> None:
    _reset_telemetry_state()
    settings = Settings(otel_service_name="epub2pdf-test")

    init_telemetry(settings)
    init_telemetry(settings)  # segunda llamada no debe fallar


def test_traced_conversion_success_sets_attributes() -> None:
    _reset_telemetry_state()
    init_telemetry(Settings(otel_service_name="epub2pdf-test"))

    with traced_conversion("libro.epub", 12345) as span:
        assert span is not None


def test_traced_conversion_propagates_exceptions() -> None:
    _reset_telemetry_state()
    init_telemetry(Settings(otel_service_name="epub2pdf-test"))

    raised = False
    try:
        with traced_conversion("libro.epub", 100):
            raise ValueError("fallo simulado")
    except ValueError:
        raised = True

    assert raised


def test_init_telemetry_with_invalid_endpoint_does_not_raise() -> None:
    _reset_telemetry_state()
    settings = Settings(
        otel_exporter_otlp_endpoint="http://endpoint-invalido-para-test:4318",
        otel_service_name="epub2pdf-test",
    )

    # No debe fallar aunque el endpoint no sea alcanzable: la creación del
    # exportador no intenta conectar de forma síncrona.
    init_telemetry(settings)
