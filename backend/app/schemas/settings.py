from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class CreateApiKeyRequest(BaseModel):
    engine: str
    key: str


class ApiKeyResponse(BaseModel):
    id: str
    engine: str
    masked_key: str
    created_at: datetime

    model_config = {"from_attributes": True}
