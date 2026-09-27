from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from uuid import UUID

from celery import chain
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.redis import publish_document_status
from app.models.document import Document, DocumentStatus
from app.models.user import IngestionJob
from app.services import extraction_service
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

_loop: asyncio.AbstractEventLoop | None = None
_engine = None
_session_factory = None


def _utcnow():
    return datetime.now(timezone.utc)


def _worker_loop() -> asyncio.AbstractEventLoop:
    global _loop
    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
    return _loop


def _run(coro):
    return _worker_loop().run_until_complete(coro)


def _sessionmaker():
    global _engine, _session_factory
    if _session_factory is None:
        _engine = create_async_engine(
            get_settings().database_url,
            pool_pre_ping=True,
        )
        _session_factory = async_sessionmaker(
            _engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
        )
    return _session_factory


@asynccontextmanager
async def worker_db():
    factory = _sessionmaker()
    async with factory() as db:
        try:
            yield db
            await db.commit()
        except Exception:
            await db.rollback()
            raise


async def _set_job(db, document_id: UUID, status: str, error: str | None = None, bump_retry: bool = False) -> None:
    result = await db.execute(
        select(IngestionJob)
        .where(IngestionJob.document_id == document_id)
        .order_by(IngestionJob.created_at.desc())
        .limit(1)
    )
    job = result.scalar_one_or_none()
    if not job:
        job = IngestionJob(document_id=document_id, status=status, error_message=error)
        db.add(job)
    else:
        job.status = status
        job.error_message = error
        if bump_retry:
            job.retry_count += 1
        job.updated_at = _utcnow()
    await db.flush()


async def _publish(db, document_id: UUID) -> None:
    doc = await db.get(Document, document_id)
    if not doc:
        return
    result = await db.execute(
        select(IngestionJob)
        .where(IngestionJob.document_id == document_id)
        .order_by(IngestionJob.created_at.desc())
        .limit(1)
    )
    job = result.scalar_one_or_none()
    await publish_document_status(
        document_id,
        {
            "document_id": str(document_id),
            "status": doc.status.value,
            "stage": doc.status.value,
            "error_message": doc.error_message,
            "needs_review": doc.status == DocumentStatus.needs_review,
            "retry_count": job.retry_count if job else 0,
        },
    )


async def _fail(document_id: UUID, message: str, retries: int) -> None:
    async with worker_db() as db:
        doc = await db.get(Document, document_id)
        if doc:
            doc.status = DocumentStatus.retrying if retries < 3 else DocumentStatus.failed
            doc.error_message = message
        await _set_job(
            db,
            document_id,
            "retrying" if retries < 3 else "failed",
            message,
            bump_retry=True,
        )
        await _publish(db, document_id)


@celery_app.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_backoff_max=60, max_retries=3)
def run_ocr_or_dicom_parse(self, document_id: str) -> str:
    async def _go():
        async with worker_db() as db:
            uid = UUID(document_id)
            await _set_job(db, uid, "running")
            await extraction_service.run_ocr_or_dicom_parse(db, uid)
            await _publish(db, uid)

    try:
        _run(_go())
    except Exception as exc:
        _run(_fail(UUID(document_id), str(exc), self.request.retries))
        raise
    return document_id


@celery_app.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_backoff_max=60, max_retries=3)
def extract_medical_entities(self, document_id: str) -> str:
    async def _go():
        async with worker_db() as db:
            uid = UUID(document_id)
            await extraction_service.extract_medical_entities(db, uid)
            await _publish(db, uid)

    try:
        _run(_go())
    except Exception as exc:
        _run(_fail(UUID(document_id), str(exc), self.request.retries))
        raise
    return document_id


@celery_app.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_backoff_max=60, max_retries=3)
def normalize_and_score(self, document_id: str) -> str:
    async def _go():
        async with worker_db() as db:
            uid = UUID(document_id)
            await extraction_service.normalize_and_score(db, uid)
            await _set_job(db, uid, "succeeded")
            await _publish(db, uid)

    try:
        _run(_go())
    except Exception as exc:
        _run(_fail(UUID(document_id), str(exc), self.request.retries))
        raise
    return document_id


@celery_app.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_backoff_max=60, max_retries=3)
def index_document_embeddings(self, document_id: str) -> str:
    async def _go():
        async with worker_db() as db:
            uid = UUID(document_id)
            from app.services import embedding_service

            await embedding_service.index_document(db, uid)

    try:
        _run(_go())
    except Exception as exc:
        logger.warning("Embedding index failed for %s: %s", document_id, exc)
        raise
    return document_id


def enqueue_ingest(document_id: str) -> None:
    chain(
        run_ocr_or_dicom_parse.s(document_id),
        extract_medical_entities.s(),
        normalize_and_score.s(),
    ).apply_async()
