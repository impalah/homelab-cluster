import pytest
from sqlalchemy.exc import IntegrityError

from apikey_service.repositories.apikey_repository import ApiKeyRepository


@pytest.fixture
def repo(db_session):
    return ApiKeyRepository(db_session)


async def test_create_persists_and_returns_the_row(repo):
    created = await repo.create("hash-1", "label-1")

    assert created.id is not None
    assert created.key_hash == "hash-1"
    assert created.label == "label-1"
    assert created.revoked_at is None
    assert created.last_used_at is None
    assert created.created_at is not None


async def test_get_by_hash_finds_existing_key(repo):
    created = await repo.create("hash-2", "label-2")

    fetched = await repo.get_by_hash("hash-2")

    assert fetched is not None
    assert fetched.id == created.id


async def test_get_by_hash_returns_none_when_missing(repo):
    assert await repo.get_by_hash("does-not-exist") is None


async def test_get_by_id_finds_and_returns_none_when_missing(repo):
    created = await repo.create("hash-3", "label-3")

    assert (await repo.get_by_id(created.id)).label == "label-3"
    assert await repo.get_by_id(999999) is None


async def test_list_all_returns_every_key_ordered_by_id(repo):
    first = await repo.create("hash-4", "a")
    second = await repo.create("hash-5", "b")

    result = await repo.list_all()

    assert [k.id for k in result] == [first.id, second.id]


async def test_revoke_sets_revoked_at(repo):
    created = await repo.create("hash-6", "label-6")
    assert created.revoked_at is None

    await repo.revoke(created.id)

    fetched = await repo.get_by_id(created.id)
    assert fetched.revoked_at is not None


async def test_touch_last_used_sets_timestamp(repo):
    created = await repo.create("hash-7", "label-7")
    assert created.last_used_at is None

    await repo.touch_last_used(created.id)

    fetched = await repo.get_by_id(created.id)
    assert fetched.last_used_at is not None


async def test_key_hash_is_unique(repo):
    await repo.create("hash-dup", "first")
    with pytest.raises(IntegrityError):
        await repo.create("hash-dup", "second")
