from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from apikey_service.dependencies import get_apikey_service
from apikey_service.services.apikey_service import ApiKeyService

router = APIRouter()


@router.get("/validate")
async def validate(
    request: Request,
    service: Annotated[ApiKeyService, Depends(get_apikey_service)],
    x_api_key: Annotated[str | None, Header()] = None,
    x_real_ip: Annotated[str | None, Header()] = None,
) -> dict:
    """Endpoint pensado para nginx auth_request (ver nginx.conf y
    docs/06-instalacion-pi1-dns.md). nginx reenvía aquí la cabecera X-Api-Key de
    la petición original y X-Real-IP con la IP real del cliente (sin esto,
    solo veríamos la IP del propio nginx, que es quien hace la subrequest);
    un 200 deja pasar, cualquier otro código (401 aquí) hace que nginx
    devuelva 401 al cliente real."""
    source_ip = x_real_ip or (request.client.host if request.client else "-")
    valid = await service.validate_key(x_api_key, source_ip)
    if not valid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    return {"status": "ok"}
