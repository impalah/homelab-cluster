from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends

from epub2pdf_service.dependencies import get_conversion_service
from epub2pdf_service.domain.models import ConversionResult, ConversionStatus
from epub2pdf_service.schemas import ConversionResultOut, ConvertRequest, ConvertResponse
from epub2pdf_service.services.conversion_service import ConversionService

router = APIRouter()

ConversionServiceDep = Annotated[ConversionService, Depends(get_conversion_service)]


def _to_result_out(result: ConversionResult) -> ConversionResultOut:
    return ConversionResultOut(
        source_path=str(result.source_path),
        output_path=str(result.output_path) if result.output_path else None,
        status=result.status.value,
        reason=result.reason.value if result.reason else None,
        message=result.message,
        duration_seconds=result.duration_seconds,
    )


def _overall_status(results: list[ConversionResult]) -> str:
    if not results:
        return "failure"
    successes = [r for r in results if r.status == ConversionStatus.SUCCESS]
    failures = [r for r in results if r.status == ConversionStatus.FAILURE]
    if failures and successes:
        return "partial_failure"
    if failures:
        return "failure"
    return "success"


@router.post("/convert")
def convert(request: ConvertRequest, service: ConversionServiceDep) -> ConvertResponse:
    """Convierte por lote los EPUB de `input_path` y los deja en
    `output_path`. Nunca lanza excepciones al llamador: cualquier fallo de
    un fichero individual se refleja en `results`, para que n8n pueda
    iterar y seguir con el resto."""
    input_path = Path(request.input_path)
    output_path = Path(request.output_path)

    if not input_path.exists():
        return ConvertResponse(status="failure", total=0, successes=0, failures=0, results=[])

    results = service.convert_batch(input_path, output_path)
    successes = [r for r in results if r.status == ConversionStatus.SUCCESS]
    failures = [r for r in results if r.status == ConversionStatus.FAILURE]

    return ConvertResponse(
        status=_overall_status(results),
        total=len(results),
        successes=len(successes),
        failures=len(failures),
        results=[_to_result_out(r) for r in results],
    )
