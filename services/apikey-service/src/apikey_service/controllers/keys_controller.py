from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from apikey_service.dependencies import get_apikey_service, require_admin
from apikey_service.schemas import (
    ApiKeyCreatedResponse,
    ApiKeyCreateRequest,
    ApiKeyResponse,
)
from apikey_service.services.apikey_service import ApiKeyService

router = APIRouter(prefix="/keys", dependencies=[Depends(require_admin)])

ApiKeyServiceDep = Annotated[ApiKeyService, Depends(get_apikey_service)]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_key(
    body: ApiKeyCreateRequest,
    service: ApiKeyServiceDep,
) -> ApiKeyCreatedResponse:
    api_key, raw_key = await service.create_key(body.label)
    return ApiKeyCreatedResponse(id=api_key.id, label=api_key.label, key=raw_key)


@router.get("")
async def list_keys(service: ApiKeyServiceDep) -> list[ApiKeyResponse]:
    keys = await service.list_keys()
    return [ApiKeyResponse.model_validate(k) for k in keys]


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_key(key_id: int, service: ApiKeyServiceDep) -> None:
    revoked = await service.revoke_key(key_id)
    if not revoked:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
