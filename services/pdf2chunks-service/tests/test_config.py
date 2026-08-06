"""Tests del módulo de configuración (pydantic-settings, prefijo PDF2CHUNKS_)."""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

from pdf2chunks_service.config import Settings

ENV_VARS = [
    "PDF2CHUNKS_HOST",
    "PDF2CHUNKS_PORT",
    "PDF2CHUNKS_OCR_CHAR_THRESHOLD",
    "PDF2CHUNKS_OCR_LANGUAGE",
    "PDF2CHUNKS_CHUNK_SIZE_TOKENS",
    "PDF2CHUNKS_CHUNK_OVERLAP_RATIO",
    "PDF2CHUNKS_CHUNKING_STRATEGY",
    "PDF2CHUNKS_OUTPUT_FORMAT",
    "PDF2CHUNKS_LOG_LEVEL",
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
    assert settings.port == 8004
    assert settings.ocr_char_threshold == 20
    assert settings.ocr_language == "eng"
    assert settings.chunk_size_tokens == 400
    assert settings.chunk_overlap_ratio == 0.15
    assert settings.chunking_strategy == "fixed_size"
    assert settings.output_format == "json"
    assert settings.log_level == "INFO"


def test_overrides_from_env() -> None:
    os.environ["PDF2CHUNKS_OCR_CHAR_THRESHOLD"] = "50"
    os.environ["PDF2CHUNKS_OCR_LANGUAGE"] = "spa"
    os.environ["PDF2CHUNKS_CHUNK_SIZE_TOKENS"] = "300"
    os.environ["PDF2CHUNKS_CHUNK_OVERLAP_RATIO"] = "0.2"
    os.environ["PDF2CHUNKS_OUTPUT_FORMAT"] = "jsonl"
    os.environ["PDF2CHUNKS_LOG_LEVEL"] = "debug"

    settings = Settings()

    assert settings.ocr_char_threshold == 50
    assert settings.ocr_language == "spa"
    assert settings.chunk_size_tokens == 300
    assert settings.chunk_overlap_ratio == 0.2
    assert settings.output_format == "jsonl"
    assert settings.log_level == "debug"
