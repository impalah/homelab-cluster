from pydantic import BaseModel


class ConvertRequest(BaseModel):
    """Cuerpo esperado por `POST /convert`."""

    input_path: str
    output_path: str


class ConversionResultOut(BaseModel):
    source_path: str
    output_path: str | None
    status: str
    reason: str | None
    message: str | None
    duration_seconds: float


class ConvertResponse(BaseModel):
    status: str
    total: int
    successes: int
    failures: int
    results: list[ConversionResultOut]


class HealthResponse(BaseModel):
    status: str
    version: str
    service: str
