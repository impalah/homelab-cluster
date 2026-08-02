from datetime import datetime

from pydantic import BaseModel


class ApiKeyCreateRequest(BaseModel):
    label: str


class ApiKeyCreatedResponse(BaseModel):
    id: int
    label: str
    key: str  # en claro, solo aparece aquí — no se puede volver a consultar


class ApiKeyResponse(BaseModel):
    id: int
    label: str
    created_at: datetime
    revoked_at: datetime | None
    last_used_at: datetime | None

    model_config = {"from_attributes": True}
