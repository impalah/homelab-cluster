from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from markitdown_service.dependencies import get_conversion_service
from markitdown_service.schemas import ConversionResponse
from markitdown_service.services.conversion_service import (
    SUPPORTED_EXTENSIONS,
    ConversionFailedError,
    ConversionProducedNoContentError,
    ConversionService,
    EmptyFileError,
    FileTooLargeError,
    UnsupportedFormatError,
)

router = APIRouter()

ConversionServiceDep = Annotated[ConversionService, Depends(get_conversion_service)]


@router.post("/convert")
async def convert(
    service: ConversionServiceDep,
    file: UploadFile = File(..., description="Documento a convertir"),
    filename_hint: str | None = Form(
        default=None,
        description="Nombre de archivo con extensión (útil si el Content-Type es genérico)",
    ),
) -> ConversionResponse:
    """
    Convierte un documento al formato Markdown.

    Formatos soportados: PDF, DOCX, XLSX, PPTX, HTML, CSV, JSON, XML,
    imágenes (JPEG, PNG, GIF, WebP), audio (MP3, WAV, OGG), ZIP.

    - **file**: archivo a convertir (multipart/form-data)
    - **filename_hint**: nombre del archivo con extensión (opcional, ayuda a detectar el formato)
    """
    original_name = filename_hint or file.filename or "documento"
    content = await file.read()

    try:
        result = service.convert(content, original_name)
    except UnsupportedFormatError as exc:
        raise HTTPException(
            status_code=415,
            detail=(
                f"Formato no soportado: '{exc.extension}'. "
                f"Formatos aceptados: {sorted(SUPPORTED_EXTENSIONS)}"
            ),
        ) from exc
    except EmptyFileError as exc:
        raise HTTPException(status_code=400, detail="El archivo está vacío.") from exc
    except FileTooLargeError as exc:
        max_mb = exc.max_bytes / 1_048_576
        raise HTTPException(
            status_code=413,
            detail=(
                f"Archivo demasiado grande ({exc.size_bytes / 1_048_576:.1f} MB). "
                f"Límite: {max_mb:.0f} MB."
            ),
        ) from exc
    except ConversionProducedNoContentError as exc:
        raise HTTPException(
            status_code=422,
            detail="La conversión no produjo contenido. El archivo puede estar vacío o corrupto.",
        ) from exc
    except ConversionFailedError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Error durante la conversión: {exc}",
        ) from exc

    return ConversionResponse(
        filename=result.filename,
        extension=result.extension,
        size_bytes=result.size_bytes,
        markdown=result.markdown,
        characters=result.characters,
    )
