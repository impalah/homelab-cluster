from pydantic import BaseModel


class ProcessRequest(BaseModel):
    """Cuerpo esperado por `POST /process`."""

    input_path: str
    output_path: str


class PdfResultOut(BaseModel):
    source_file: str
    success: bool
    output_file: str | None
    chunk_count: int
    error: str | None
    warnings: list[str]


class ProcessResponse(BaseModel):
    status: str
    total: int
    successes: int
    failures: int
    results: list[PdfResultOut]


class HealthResponse(BaseModel):
    status: str
    version: str
    service: str
