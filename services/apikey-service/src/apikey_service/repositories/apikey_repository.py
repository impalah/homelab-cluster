from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from apikey_service.models import ApiKey


class ApiKeyRepository:
    """Acceso a datos puro — sin reglas de negocio (esas viven en el service)."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(self, key_hash: str, label: str) -> ApiKey:
        api_key = ApiKey(key_hash=key_hash, label=label)
        self._session.add(api_key)
        await self._session.commit()
        await self._session.refresh(api_key)
        return api_key

    async def get_by_hash(self, key_hash: str) -> ApiKey | None:
        result = await self._session.execute(select(ApiKey).where(ApiKey.key_hash == key_hash))
        return result.scalar_one_or_none()

    async def get_by_id(self, key_id: int) -> ApiKey | None:
        result = await self._session.execute(select(ApiKey).where(ApiKey.id == key_id))
        return result.scalar_one_or_none()

    async def list_all(self) -> list[ApiKey]:
        result = await self._session.execute(select(ApiKey).order_by(ApiKey.id))
        return list(result.scalars().all())

    async def revoke(self, key_id: int) -> None:
        await self._session.execute(
            update(ApiKey).where(ApiKey.id == key_id).values(revoked_at=datetime.now(UTC))
        )
        await self._session.commit()

    async def touch_last_used(self, key_id: int) -> None:
        await self._session.execute(
            update(ApiKey).where(ApiKey.id == key_id).values(last_used_at=datetime.now(UTC))
        )
        await self._session.commit()
