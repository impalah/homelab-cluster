"""Router de `POST /process` — traduce `ProcessingResult` (dominio) a
`ProcessResponse` (API) y delega la escritura a disco en
`infrastructure.chunk_writer`, igual que `convert_controller` en
epub2pdf-service delega en su `ConversionService`."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends

from pdf2chunks_service.config import settings
from pdf2chunks_service.dependencies import get_processing_service
from pdf2chunks_service.infrastructure import chunk_writer
from pdf2chunks_service.schemas import PdfResultOut, ProcessRequest, ProcessResponse
from pdf2chunks_service.services.pdf_processing_service import PdfProcessingService

router = APIRouter()


@router.post("/process", response_model=ProcessResponse)
async def process(
    request: ProcessRequest,
    service: PdfProcessingService = Depends(get_processing_service),
) -> ProcessResponse:
    results = service.process_batch(Path(request.input_path))
    output_dir = Path(request.output_path)

    results_out: list[PdfResultOut] = []
    successes = 0
    failures = 0

    for result in results:
        output_file = None
        if result.success:
            successes += 1
            written = chunk_writer.write_result(result, output_dir, settings.output_format)
            output_file = str(written) if written else None
        else:
            failures += 1

        results_out.append(
            PdfResultOut(
                source_file=result.source_file,
                success=result.success,
                output_file=output_file,
                chunk_count=len(result.chunks),
                error=result.error,
                warnings=result.warnings,
            )
        )

    if not results:
        status = "failure"
    elif failures == 0:
        status = "success"
    elif successes == 0:
        status = "failure"
    else:
        status = "partial_failure"

    return ProcessResponse(
        status=status,
        total=len(results),
        successes=successes,
        failures=failures,
        results=results_out,
    )
