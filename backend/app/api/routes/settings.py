from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.security import decrypt_api_key, encrypt_api_key, mask_api_key
from app.models.api_key import ApiKey
from app.models.user import User
from app.schemas.settings import ApiKeyResponse, CreateApiKeyRequest

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/api-keys", response_model=List[ApiKeyResponse])
def list_api_keys(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    keys = db.query(ApiKey).filter(ApiKey.user_id == current_user.id).all()
    result = []
    for k in keys:
        try:
            plain = decrypt_api_key(k.encrypted_key)
            masked = mask_api_key(plain)
        except Exception:
            masked = "****"
        result.append(
            ApiKeyResponse(
                id=k.id,
                engine=k.engine,
                masked_key=masked,
                created_at=k.created_at,
            )
        )
    return result


@router.post("/api-keys", response_model=ApiKeyResponse, status_code=status.HTTP_201_CREATED)
def create_api_key(
    body: CreateApiKeyRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    valid_engines = {"anthropic", "google", "azure", "deepl"}
    if body.engine not in valid_engines:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid engine. Must be one of: {', '.join(valid_engines)}",
        )

    existing = db.query(ApiKey).filter(
        ApiKey.user_id == current_user.id, ApiKey.engine == body.engine
    ).first()
    if existing:
        # Update existing key
        existing.encrypted_key = encrypt_api_key(body.key)
        existing.created_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(existing)
        masked = mask_api_key(body.key)
        return ApiKeyResponse(
            id=existing.id,
            engine=existing.engine,
            masked_key=masked,
            created_at=existing.created_at,
        )

    encrypted = encrypt_api_key(body.key)
    api_key = ApiKey(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        engine=body.engine,
        encrypted_key=encrypted,
        created_at=datetime.now(timezone.utc),
    )
    db.add(api_key)
    db.commit()
    db.refresh(api_key)

    masked = mask_api_key(body.key)
    return ApiKeyResponse(
        id=api_key.id,
        engine=api_key.engine,
        masked_key=masked,
        created_at=api_key.created_at,
    )


@router.delete("/api-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_api_key(
    key_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    api_key = db.query(ApiKey).filter(
        ApiKey.id == key_id, ApiKey.user_id == current_user.id
    ).first()
    if not api_key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")
    db.delete(api_key)
    db.commit()
