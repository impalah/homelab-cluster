"""Tests del módulo de configuración (pydantic-settings, prefijo EPUB2PDF_)."""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

from epub2pdf_service.config import Settings

ENV_VARS = [
    "EPUB2PDF_HOST",
    "EPUB2PDF_PORT",
    "EPUB2PDF_INPUT_PATH",
    "EPUB2PDF_OUTPUT_PATH",
    "EPUB2PDF_CALIBRE_BINARY",
    "EPUB2PDF_CONVERSION_TIMEOUT_SECONDS",
    "EPUB2PDF_MAX_FILENAME_COLLISION_ATTEMPTS",
    "EPUB2PDF_LOG_LEVEL",
    "EPUB2PDF_OTEL_ENABLED",
    "EPUB2PDF_OTEL_EXPORTER_OTLP_ENDPOINT",
    "EPUB2PDF_OTEL_SERVICE_NAME",
]


@pytest.fixture(autouse=True)
def _clean_env() -> Iterator[None]:
    previous = {var: os.environ.get(var) for var in ENV_VARS}
    for var in ENV_VARS:
        os.environ.pop(var, None)
    yield
    for var, value in previous.items():
        if value is None:
            os.environ.pop(var, None)
        else:
            os.environ[var] = value


def test_defaults_when_no_env_vars_set() -> None:
    settings = Settings()

    assert settings.host == "0.0.0.0"
    assert settings.port == 8003
    assert settings.input_path == "/data/input"
    assert settings.output_path == "/data/output"
    assert settings.calibre_binary == "ebook-convert"
    assert settings.conversion_timeout_seconds == 300
    assert settings.max_filename_collision_attempts == 1000
    assert settings.log_level == "INFO"
    assert settings.otel_enabled is True
    assert settings.otel_exporter_otlp_endpoint is None
    assert settings.otel_service_name == "epub2pdf-service"


def test_overrides_from_env() -> None:
    os.environ["EPUB2PDF_INPUT_PATH"] = "/custom/input"
    os.environ["EPUB2PDF_OUTPUT_PATH"] = "/custom/output"
    os.environ["EPUB2PDF_CALIBRE_BINARY"] = "/opt/calibre/ebook-convert"
    os.environ["EPUB2PDF_CONVERSION_TIMEOUT_SECONDS"] = "60"
    os.environ["EPUB2PDF_LOG_LEVEL"] = "debug"
    os.environ["EPUB2PDF_OTEL_EXPORTER_OTLP_ENDPOINT"] = "http://collector:4318"
    os.environ["EPUB2PDF_OTEL_SERVICE_NAME"] = "custom-service"
    os.environ["EPUB2PDF_OTEL_ENABLED"] = "false"
    os.environ["EPUB2PDF_MAX_FILENAME_COLLISION_ATTEMPTS"] = "5"

    settings = Settings()

    assert settings.input_path == "/custom/input"
    assert settings.output_path == "/custom/output"
    assert settings.calibre_binary == "/opt/calibre/ebook-convert"
    assert settings.conversion_timeout_seconds == 60
    assert settings.log_level == "debug"
    assert settings.otel_exporter_otlp_endpoint == "http://collector:4318"
    assert settings.otel_service_name == "custom-service"
    assert settings.otel_enabled is False
    assert settings.max_filename_collision_attempts == 5
