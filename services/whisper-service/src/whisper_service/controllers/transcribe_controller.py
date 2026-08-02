from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from whisper_service.config import settings
from whisper_service.dependencies import get_transcription_service
from whisper_service.schemas import TranscriptionResponse
from whisper_service.services.transcription_service import (
    ALLOWED_CONTENT_TYPES,
    EmptyAudioError,
    ModelNotLoadedError,
    TranscriptionFailedError,
    TranscriptionService,
    UnsupportedContentTypeError,
)

router = APIRouter()

TranscriptionServiceDep = Annotated[TranscriptionService, Depends(get_transcription_service)]


@router.post(
    "/transcribe",
    responses={
        400: {"description": "El archivo de audio está vacío."},
        415: {"description": "Tipo de contenido no soportado."},
        500: {"description": "Error durante la transcripción."},
        503: {"description": "El modelo aún no está cargado."},
    },
)
async def transcribe(
    service: TranscriptionServiceDep,
    file: UploadFile = File(..., description="Archivo de audio (mp3, wav, ogg, m4a, flac)"),
    language: str | None = Form(
        default=None,
        description=(
            "Código de idioma ISO 639-1 (ej: 'es', 'en'). Si se omite, usa el valor por defecto."
        ),
    ),
    task: str = Form(
        default="transcribe",
        description="'transcribe' para transcripción, 'translate' para traducir al inglés",
    ),
) -> TranscriptionResponse:
    """
    Transcribe un archivo de audio y devuelve el texto resultante.

    - **file**: audio en formato mp3, wav, ogg, m4a o flac
    - **language**: idioma del audio (por defecto el configurado en `WHISPER_LANGUAGE`)
    - **task**: `transcribe` o `translate`
    """
    content = await file.read()
    lang = language or settings.whisper_language

    try:
        result = await service.transcribe(content, file.content_type, file.filename, lang, task)
    except ModelNotLoadedError as exc:
        raise HTTPException(
            status_code=503, detail="Modelo no cargado aún. Reintenta en unos segundos."
        ) from exc
    except UnsupportedContentTypeError as exc:
        raise HTTPException(
            status_code=415,
            detail=(
                f"Tipo de archivo no soportado: '{exc.content_type}'. "
                f"Tipos aceptados: {sorted(ALLOWED_CONTENT_TYPES)}"
            ),
        ) from exc
    except EmptyAudioError as exc:
        raise HTTPException(status_code=400, detail="El archivo de audio está vacío.") from exc
    except TranscriptionFailedError as exc:
        raise HTTPException(status_code=500, detail=f"Error de transcripción: {exc}") from exc

    return TranscriptionResponse(
        text=result.text,
        language=result.language,
        language_probability=result.language_probability,
        duration=result.duration,
        model=settings.whisper_model,
    )
