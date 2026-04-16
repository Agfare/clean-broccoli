from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone

import bcrypt
from cryptography.fernet import Fernet
from jose import JWTError, jwt

from app.core.config import settings

ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None


def _get_fernet() -> Fernet:
    key = settings.ENCRYPTION_KEY
    # Accept raw base64url Fernet key or plain string padded to 32 bytes
    try:
        return Fernet(key.encode() if isinstance(key, str) else key)
    except Exception:
        # Fallback: derive a valid Fernet key from the string
        padded = key.encode("utf-8")[:32].ljust(32, b"\x00")
        b64_key = base64.urlsafe_b64encode(padded)
        return Fernet(b64_key)


def encrypt_api_key(key: str) -> str:
    f = _get_fernet()
    encrypted = f.encrypt(key.encode("utf-8"))
    return encrypted.decode("utf-8")


def decrypt_api_key(encrypted: str) -> str:
    f = _get_fernet()
    decrypted = f.decrypt(encrypted.encode("utf-8"))
    return decrypted.decode("utf-8")


def mask_api_key(key: str) -> str:
    if len(key) <= 8:
        return "*" * len(key)
    return key[:4] + "*" * (len(key) - 8) + key[-4:]
