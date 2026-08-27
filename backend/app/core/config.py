from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Patient Health Intelligence Platform"
    debug: bool = False
    database_url: str = (
        "postgresql+asyncpg://health:health_dev_password@localhost:5432/health_intelligence"
    )

    jwt_private_key_path: str = "../keys/jwt_private.pem"
    jwt_public_key_path: str = "../keys/jwt_public.pem"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    secret_key: str = "change-me"
    frontend_url: str = "http://localhost:5173"
    cors_origins: List[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )
    inactivity_timeout_minutes: int = 15

    def _resolve_key_path(self, path: str) -> Path:
        p = Path(path)
        if p.is_absolute():
            return p
        # Prefer relative to backend/, then repo root
        candidates = [
            BACKEND_DIR / p,
            BACKEND_DIR.parent / p.relative_to("..") if str(p).startswith("..") else BACKEND_DIR / p,
            BACKEND_DIR.parent / "keys" / p.name,
        ]
        for c in candidates:
            if c.exists():
                return c
        return BACKEND_DIR / p

    @property
    def jwt_private_key(self) -> str:
        return self._resolve_key_path(self.jwt_private_key_path).read_text()

    @property
    def jwt_public_key(self) -> str:
        return self._resolve_key_path(self.jwt_public_key_path).read_text()


@lru_cache
def get_settings() -> Settings:
    return Settings()
