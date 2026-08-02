import hashlib
import secrets

from apikey_service.logging_setup import audit_logger
from apikey_service.models import ApiKey
from apikey_service.repositories.apikey_repository import ApiKeyRepository


def _hash(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


class ApiKeyService:
    """Reglas de negocio: generación/hashing de keys, validación, revocado.
    No conoce SQLAlchemy ni FastAPI — solo habla con el repositorio."""

    def __init__(self, repository: ApiKeyRepository):
        self._repository = repository

    async def create_key(self, label: str) -> tuple[ApiKey, str]:
        raw_key = secrets.token_urlsafe(32)
        api_key = await self._repository.create(_hash(raw_key), label)
        return api_key, raw_key

    async def list_keys(self) -> list[ApiKey]:
        return await self._repository.list_all()

    async def revoke_key(self, key_id: int) -> bool:
        api_key = await self._repository.get_by_id(key_id)
        if api_key is None:
            return False
        await self._repository.revoke(key_id)
        return True

    async def validate_key(self, raw_key: str | None, source_ip: str) -> bool:
        if not raw_key:
            audit_logger.warning(
                "apikey validation failed: missing key", extra={"source_ip": source_ip}
            )
            return False

        api_key = await self._repository.get_by_hash(_hash(raw_key))
        if api_key is None:
            audit_logger.warning(
                "apikey validation failed: unknown key", extra={"source_ip": source_ip}
            )
            return False

        if api_key.revoked_at is not None:
            audit_logger.warning(
                "apikey validation failed: revoked key (id=%s, label=%s)",
                api_key.id,
                api_key.label,
                extra={"source_ip": source_ip},
            )
            return False

        await self._repository.touch_last_used(api_key.id)
        return True
