"""Tests unitarios de los modelos de dominio (Pydantic), centrados en
`ScrapeParams` — la validación de los overrides opcionales por petición."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from crawl4ai_scraper_service.domain.models import ScrapeParams, ScrapeRequest


def test_scrape_params_all_fields_default_to_none() -> None:
    params = ScrapeParams()

    assert params.stealth_mode is None
    assert params.undetected_browser is None
    assert params.magic_mode is None
    assert params.wait_until is None
    assert params.page_timeout_ms is None
    assert params.word_count_threshold is None
    assert params.max_retries is None


def test_scrape_params_accepts_string_boolean_like_the_documented_example() -> None:
    """Mismo formato que el ejemplo real de uso: {"stealth_mode": "true"}."""
    params = ScrapeParams.model_validate({"stealth_mode": "true"})

    assert params.stealth_mode is True


def test_scrape_params_rejects_unknown_field() -> None:
    with pytest.raises(ValidationError):
        ScrapeParams.model_validate({"stealh_mode": True})  # typo a propósito


def test_scrape_params_rejects_invalid_wait_until_value() -> None:
    with pytest.raises(ValidationError):
        ScrapeParams.model_validate({"wait_until": "instantaneous"})


def test_scrape_params_rejects_negative_page_timeout() -> None:
    with pytest.raises(ValidationError):
        ScrapeParams.model_validate({"page_timeout_ms": -1})


def test_scrape_params_rejects_negative_word_count_threshold() -> None:
    with pytest.raises(ValidationError):
        ScrapeParams.model_validate({"word_count_threshold": -1})


def test_scrape_request_params_defaults_to_none() -> None:
    request = ScrapeRequest.model_validate({"url": "https://example.com"})

    assert request.params is None


def test_scrape_request_accepts_nested_params() -> None:
    request = ScrapeRequest.model_validate(
        {"url": "https://example.com", "params": {"undetected_browser": True, "max_retries": 0}}
    )

    assert request.params is not None
    assert request.params.undetected_browser is True
    assert request.params.max_retries == 0
