from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from apikey_service.models import ApiKey
from apikey_service.services.apikey_service import ApiKeyService, _hash


@pytest.fixture
def mock_repo():
    return AsyncMock()


@pytest.fixture
def service(mock_repo):
    return ApiKeyService(mock_repo)


async def test_create_key_returns_raw_key_and_stores_only_the_hash(service, mock_repo):
    stored = ApiKey(id=1, key_hash="whatever-stored", label="ci")
    mock_repo.create.return_value = stored

    api_key, raw_key = await service.create_key("ci")

    assert api_key is stored
    assert len(raw_key) > 20  # secrets.token_urlsafe(32)
    called_hash, called_label = mock_repo.create.call_args.args
    assert called_hash == _hash(raw_key)
    assert called_label == "ci"
    # el hash nunca es el propio valor en claro
    assert called_hash != raw_key


async def test_create_key_hash_is_deterministic_sha256():
    assert _hash("abc") == _hash("abc")
    assert _hash("abc") != _hash("abd")
    assert len(_hash("abc")) == 64  # hex de sha256


async def test_list_keys_delegates_to_repository(service, mock_repo):
    expected = [ApiKey(id=1, label="a"), ApiKey(id=2, label="b")]
    mock_repo.list_all.return_value = expected

    result = await service.list_keys()

    assert result == expected
    mock_repo.list_all.assert_awaited_once()


async def test_revoke_key_returns_false_when_not_found(service, mock_repo):
    mock_repo.get_by_id.return_value = None

    result = await service.revoke_key(99)

    assert result is False
    mock_repo.revoke.assert_not_called()


async def test_revoke_key_returns_true_and_revokes_when_found(service, mock_repo):
    mock_repo.get_by_id.return_value = ApiKey(id=1, label="ci")

    result = await service.revoke_key(1)

    assert result is True
    mock_repo.revoke.assert_awaited_once_with(1)


async def test_validate_key_false_when_key_missing(service, mock_repo):
    assert await service.validate_key(None, "10.0.0.1") is False
    assert await service.validate_key("", "10.0.0.1") is False
    mock_repo.get_by_hash.assert_not_called()


async def test_validate_key_false_when_unknown(service, mock_repo):
    mock_repo.get_by_hash.return_value = None

    assert await service.validate_key("somekey", "10.0.0.1") is False
    mock_repo.touch_last_used.assert_not_called()


async def test_validate_key_false_when_revoked(service, mock_repo):
    mock_repo.get_by_hash.return_value = ApiKey(id=1, label="ci", revoked_at=datetime.now(UTC))

    assert await service.validate_key("somekey", "10.0.0.1") is False
    mock_repo.touch_last_used.assert_not_called()


async def test_validate_key_true_and_touches_last_used_when_valid(service, mock_repo):
    mock_repo.get_by_hash.return_value = ApiKey(id=42, label="ci", revoked_at=None)

    assert await service.validate_key("somekey", "10.0.0.1") is True
    mock_repo.touch_last_used.assert_awaited_once_with(42)
