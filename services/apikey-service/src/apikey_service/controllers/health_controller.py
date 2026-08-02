from fastapi import APIRouter

from apikey_service import __version__

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "version": __version__,
        "service": "apikey-service",
    }
