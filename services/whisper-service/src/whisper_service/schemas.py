from pydantic import BaseModel


class TranscriptionResponse(BaseModel):
    text: str
    language: str
    language_probability: float
    duration: float
    model: str


class HealthResponse(BaseModel):
    status: str
    version: str
    service: str
    model: str
    device: str
    compute_type: str
    language: str
