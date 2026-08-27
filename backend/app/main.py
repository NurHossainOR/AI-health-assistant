from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.v1 import api_router
from app.core.config import get_settings
from app.core.exceptions import AppError, app_error_handler
from app.db.session import Base, engine
from app.models import (  # noqa: F401 — register models on metadata
    AuditLog,
    ConsentGrant,
    DoctorProfile,
    IngestionJob,
    PasswordResetToken,
    PatientProfile,
    RefreshToken,
    User,
)

logging.basicConfig(level=logging.INFO)
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
]


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # App role bypasses RLS for API layer; policies still defend direct DB access
        await conn.execute(text("SET app.bypass_rls = 'on'"))
        for stmt in RLS_SQL:
            try:
                await conn.execute(text(stmt))
            except Exception as exc:  # noqa: BLE001
                logger.warning("RLS statement skipped/failed: %s (%s)", stmt[:60], exc)
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

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


app = create_app()
