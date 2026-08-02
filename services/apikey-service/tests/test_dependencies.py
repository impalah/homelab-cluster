from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from apikey_service.config import settings
from apikey_service.dependencies import require_admin


def _make_request(client_host: str | None = "10.0.0.1") -> MagicMock:
    request = MagicMock()
    request.url.path = "/keys"
    if client_host is None:
        request.client = None
    else:
        request.client.host = client_host
    return request


async def test_require_admin_raises_401_when_header_missing():
    with pytest.raises(HTTPException) as exc_info:
        await require_admin(_make_request(), authorization=None)
    assert exc_info.value.status_code == 401


async def test_require_admin_raises_401_when_header_not_bearer():
    with pytest.raises(HTTPException) as exc_info:
        await require_admin(_make_request(), authorization="Basic xxxx")
    assert exc_info.value.status_code == 401


async def test_require_admin_raises_401_when_token_wrong():
    with pytest.raises(HTTPException) as exc_info:
        await require_admin(_make_request(), authorization="Bearer wrong-token")
    assert exc_info.value.status_code == 401


async def test_require_admin_passes_with_correct_token():
    # No lanza excepción
    await require_admin(_make_request(), authorization=f"Bearer {settings.admin_token}")


async def test_require_admin_handles_missing_client_on_failure():
    # request.client puede ser None (algunos entornos ASGI de test) — no debe petar al loguear
    with pytest.raises(HTTPException):
        await require_admin(_make_request(client_host=None), authorization=None)
