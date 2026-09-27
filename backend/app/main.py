from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.v1 import api_router
from app.api.v1 import ws as ws_routes
from app.core.config import get_settings
from app.core.exceptions import AppError, app_error_handler
from app.db.session import Base, engine
from app.models import (  # noqa: F401 — register models on metadata
    AuditLog,
    ChatMessage,
    ChatSession,
    ConsentGrant,
    DoctorProfile,
    Document,
    DocumentPage,
    ExtractedField,
    ImagingStudy,
    IngestionJob,
    PasswordResetToken,
    PatientProfile,
    RefreshToken,
    User,
)
from app.services import storage_service

logging.basicConfig(level=logging.WARNING)
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy.pool").setLevel(logging.WARNING)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
logging.getLogger("chromadb").setLevel(logging.ERROR)
logging.getLogger("chromadb.telemetry").setLevel(logging.CRITICAL)
logger = logging.getLogger(__name__)


RLS_SQL = [
    "ALTER TABLE consent_grants ENABLE ROW LEVEL SECURITY",
    "DROP POLICY IF EXISTS consent_grants_patient_or_grantee ON consent_grants",
    """
    CREATE POLICY consent_grants_patient_or_grantee ON consent_grants
      USING (
        patient_id::text = current_setting('app.current_user_id', true)
        OR grantee_id::text = current_setting('app.current_user_id', true)
        OR current_setting('app.bypass_rls', true) = 'on'
      )
    """,
    "ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY",
    "DROP POLICY IF EXISTS audit_logs_admin_or_actor ON audit_logs",
    """
    CREATE POLICY audit_logs_admin_or_actor ON audit_logs
      FOR SELECT
      USING (
        actor_id::text = current_setting('app.current_user_id', true)
        OR current_setting('app.bypass_rls', true) = 'on'
      )
    """,
    "DROP POLICY IF EXISTS audit_logs_insert ON audit_logs",
    """
    CREATE POLICY audit_logs_insert ON audit_logs
      FOR INSERT
      WITH CHECK (true)
    """,
    "ALTER TABLE documents ENABLE ROW LEVEL SECURITY",
    "DROP POLICY IF EXISTS documents_patient_scope ON documents",
    """
    CREATE POLICY documents_patient_scope ON documents
      USING (
        patient_id::text = current_setting('app.current_user_id', true)
        OR current_setting('app.bypass_rls', true) = 'on'
      )
    """,
    "ALTER TABLE chat_sessions ENABLE ROW LEVEL SECURITY",
    "DROP POLICY IF EXISTS chat_sessions_patient_scope ON chat_sessions",
    """
    CREATE POLICY chat_sessions_patient_scope ON chat_sessions
      USING (
        patient_id::text = current_setting('app.current_user_id', true)
        OR current_setting('app.bypass_rls', true) = 'on'
      )
    """,
    "ALTER TABLE chat_messages ENABLE ROW LEVEL SECURITY",
    "DROP POLICY IF EXISTS chat_messages_patient_scope ON chat_messages",
    """
    CREATE POLICY chat_messages_patient_scope ON chat_messages
      USING (
        EXISTS (
          SELECT 1 FROM chat_sessions s
          WHERE s.id = chat_messages.session_id
            AND (
              s.patient_id::text = current_setting('app.current_user_id', true)
              OR current_setting('app.bypass_rls', true) = 'on'
            )
        )
        OR current_setting('app.bypass_rls', true) = 'on'
      )
    """,
]

SCHEMA_PATCHES = [
    "ALTER TABLE patient_profiles ADD COLUMN IF NOT EXISTS processing_consent_at TIMESTAMPTZ",
    """
    DO $$
    BEGIN
      IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'doctor_profiles' AND column_name = 'npi_number'
      ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'doctor_profiles'
          AND column_name = 'bmdc_registration_number'
      ) THEN
        ALTER TABLE doctor_profiles RENAME COLUMN npi_number TO bmdc_registration_number;
      END IF;
    END $$
    """,
    "ALTER TABLE doctor_profiles ADD COLUMN IF NOT EXISTS bmdc_registration_number VARCHAR(20)",
    "DROP INDEX IF EXISTS ix_doctor_profiles_npi_number",
    "CREATE INDEX IF NOT EXISTS ix_doctor_profiles_bmdc_registration_number ON doctor_profiles (bmdc_registration_number)",
    "ALTER TABLE documents ADD COLUMN IF NOT EXISTS display_name VARCHAR(255)",
    "ALTER TABLE documents ADD COLUMN IF NOT EXISTS indexed_at TIMESTAMPTZ",
    "ALTER TYPE consent_scope ADD VALUE IF NOT EXISTS 'document'",
]


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        await conn.run_sync(Base.metadata.create_all)
        # App role bypasses RLS for API layer; policies still defend direct DB access
        await conn.execute(text("SET app.bypass_rls = 'on'"))
        for stmt in SCHEMA_PATCHES + RLS_SQL:
            try:
                async with conn.begin_nested():
                    await conn.execute(text(stmt))
            except Exception as exc:  # noqa: BLE001
                logger.warning("Schema/RLS statement skipped/failed: %s (%s)", stmt[:60], exc)
    try:
        storage_service.probe_bucket()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Object storage probe skipped: %s", type(exc).__name__)
    logger.info("Database schema ready")


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_db()
    yield
    await engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.add_exception_handler(AppError, app_error_handler)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router)
    app.include_router(ws_routes.router)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


app = create_app()
