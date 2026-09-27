from functools import lru_cache
from pathlib import Path
from typing import List
from urllib.parse import urlparse

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
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
        default_factory=lambda: [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ]
    )
    inactivity_timeout_minutes: int = 15

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    smtp_from_name: str = "Spondon"
    smtp_use_tls: bool = True
    smtp_use_ssl: bool = False
    # Enforce verified email before uploads. Off in local/dev; set true in production.
    require_email_verification: bool = False

    redis_url: str = "redis://localhost:6380/0"
    celery_broker_url: str = "redis://localhost:6380/0"

    # Backblaze B2 (S3-compatible). No credential defaults — fail closed.
    b2_key_id: str = Field(
        default="",
        validation_alias=AliasChoices("B2_KEY_ID", "B2_ACCESS_KEY_ID"),
    )
    b2_application_key: str = Field(
        default="",
        validation_alias=AliasChoices("B2_APPLICATION_KEY", "B2_SECRET_ACCESS_KEY"),
    )
    b2_bucket: str = ""
    b2_endpoint_url: str = ""
    b2_region: str = ""
    presigned_url_expire_seconds: int = 600
    max_upload_bytes: int = 25 * 1024 * 1024
    extraction_confidence_threshold: float = 0.75

    gemini_api_key: str = ""
    gemini_chat_model: str = "gemini-3-flash-preview"
    gemini_embedding_model: str = "models/gemini-embedding-001"
    # OpenRouter fallbacks, tried in order when Gemini fails or is out of quota. Comma-separated.
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_text_models: str = (
        "nvidia/nemotron-3-ultra-550b-a55b:free,"
        "google/gemma-4-31b-it:free,"
        "qwen/qwen3.8-27b:free"
    )
    # Must accept image input (used for scanned-report extraction).
    openrouter_vision_models: str = (
        "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free,"
        "qwen/qwen3.8-27b:free,"
        "google/gemma-4-31b-it:free"
    )
    llm_timeout_seconds: float = 90.0
    rag_top_k: int = 6
    rag_history_turns: int = 10
    chroma_host: str = "localhost"
    chroma_port: int = 8001
    chroma_collection: str = "patient_record_chunks"

    @property
    def openrouter_text_model_list(self) -> list[str]:
        return [m.strip() for m in self.openrouter_text_models.split(",") if m.strip()]

    @property
    def openrouter_vision_model_list(self) -> list[str]:
        return [m.strip() for m in self.openrouter_vision_models.split(",") if m.strip()]

    @property
    def b2_s3_endpoint(self) -> str:
        if self.b2_endpoint_url:
            return self.b2_endpoint_url.rstrip("/")
        if self.b2_region:
            return f"https://s3.{self.b2_region}.backblazeb2.com"
        return ""

    @property
    def b2_s3_region(self) -> str:
        if self.b2_region:
            return self.b2_region
        host = (urlparse(self.b2_s3_endpoint).hostname or "").split(".")
        if len(host) >= 4 and host[0] == "s3":
            return host[1]
        return ""

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
