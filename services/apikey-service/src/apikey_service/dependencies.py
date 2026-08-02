import secrets
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from apikey_service.config import settings
from apikey_service.db import get_session
from apikey_service.logging_setup import audit_logger
from apikey_service.repositories.apikey_repository import ApiKeyRepository
from apikey_service.services.apikey_service import ApiKeyService


async def get_apikey_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ApiKeyService:
    return ApiKeyService(ApiKeyRepository(session))


async def require_admin(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    """Protege POST/GET/DELETE /keys. No usado por /validate."""
    token = ""
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:]

    if not token or not secrets.compare_digest(token, settings.admin_token):
        audit_logger.warning(
            "admin auth failed on %s",
            request.url.path,
            extra={"source_ip": request.client.host if request.client else "-"},
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid admin token")
