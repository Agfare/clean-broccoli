from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    SECRET_KEY: str
    ENCRYPTION_KEY: str
    DATABASE_URL: str = "sqlite:///./tmclean.db"
    REDIS_URL: str = "redis://localhost:6379/0"
    STORAGE_PATH: str = "./storage"
    MAX_FILE_SIZE_MB: int = 150
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7


settings = Settings()
