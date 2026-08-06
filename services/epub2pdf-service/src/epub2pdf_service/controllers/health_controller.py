from fastapi import APIRouter

from epub2pdf_service import __version__

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "version": __version__,
        "service": "epub2pdf-service",
    }
