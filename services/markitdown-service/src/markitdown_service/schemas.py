from pydantic import BaseModel


class ConversionResponse(BaseModel):
    filename: str
    extension: str
    size_bytes: int
    markdown: str
    characters: int


class HealthResponse(BaseModel):
    status: str
    version: str
    service: str
