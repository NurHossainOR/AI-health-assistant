from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.core.redis import publish_document_status
from app.models.document import DocType, Document, DocumentStatus, ExtractedField
from app.models.user import IngestionJob, PatientProfile, User, UserRole
from app.schemas.documents import (
    DocumentOut,
    DocumentPatch,
    DocumentStatusOut,
    ExtractedFieldIn,
    ExtractedFieldOut,
    UploadUrlRequest,
    UploadUrlResponse,
)
from app.services import dicom_preview, storage_service
from app.services.audit_service import write_audit_log
from app.services.consent_service import can_access_document

logger = logging.getLogger(__name__)

ALLOWED_EXT = {"pdf", "jpg", "jpeg", "png", "dcm"}
ALLOWED_MIME = {
    "application/pdf",
    "image/jpeg",
    "image/jpg",
    "image/png",
    "application/dicom",
    "application/octet-stream",
}
HINT_TO_TYPE = {
    "blood_test": DocType.blood_test,
    "blood test": DocType.blood_test,
    "prescription": DocType.prescription,
    "mri": DocType.mri,
    "ct": DocType.ct,
    "discharge": DocType.discharge,
    "discharge_summary": DocType.discharge,
    "other": DocType.other,
    "auto": None,
    "auto-detect": None,
}

STAGE_LABELS = {
    DocumentStatus.awaiting_upload: "Preparing",
    DocumentStatus.uploaded: "Uploaded",
    DocumentStatus.pending: "Uploaded",
    DocumentStatus.scanning: "Scanning",
    DocumentStatus.extracting: "Extracting",
    DocumentStatus.validating: "Validating",
    DocumentStatus.needs_review: "Needs review",
    DocumentStatus.extracted: "Ready",
    DocumentStatus.confirmed: "Ready",
    DocumentStatus.failed: "Failed",
    DocumentStatus.retrying: "Retrying",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _guess_doc_type(filename: str, mime_type: str, hint: Optional[str]) -> DocType:
    if hint:
        mapped = HINT_TO_TYPE.get(hint.strip().lower())
        if mapped:
            return mapped
    name = filename.lower()
    if name.endswith(".dcm") or mime_type == "application/dicom":
        return DocType.mri
    if "prescription" in name or "rx" in name:
        return DocType.prescription
    if "discharge" in name:
        return DocType.discharge
    if any(k in name for k in ("lipid", "lab", "blood", "hba1c", "cbc")):
        return DocType.blood_test
    if "ct" in name:
        return DocType.ct
    if "mri" in name:
        return DocType.mri
    return DocType.other


def _validate_file(filename: str, mime_type: str, file_size: int) -> None:
    settings = get_settings()
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_EXT:
        raise AppError(
            f"File type .{ext or '?'} is not allowed. Use PDF, JPG, PNG, or DICOM.",
            status_code=400,
            code="invalid_type",
        )
    if mime_type.lower() not in ALLOWED_MIME:
        raise AppError("Unsupported MIME type", status_code=400, code="invalid_mime")
    if file_size > settings.max_upload_bytes:
        raise AppError("File exceeds 25MB limit", status_code=400, code="too_large")


async def require_processing_consent(db: AsyncSession, user: User) -> None:
    if user.role != UserRole.patient:
        return
    profile = await db.get(PatientProfile, user.id)
    if not profile or profile.processing_consent_at is None:
        raise AppError(
            "Accept data-processing consent before uploading",
            status_code=403,
            code="processing_consent_required",
        )


async def _status_payload(db: AsyncSession, doc: Document) -> dict:
    job = await _latest_job(db, doc.id)
    return {
        "document_id": str(doc.id),
        "status": doc.status.value,
        "stage": STAGE_LABELS.get(doc.status, doc.status.value),
        "error_message": doc.error_message,
        "needs_review": doc.status == DocumentStatus.needs_review,
        "retry_count": job.retry_count if job else 0,
    }


async def _latest_job(db: AsyncSession, document_id: UUID) -> Optional[IngestionJob]:
    result = await db.execute(
        select(IngestionJob)
        .where(IngestionJob.document_id == document_id)
        .order_by(IngestionJob.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


def _to_out(doc: Document, retry_count: int = 0) -> DocumentOut:
    return DocumentOut(
        id=doc.id,
        patient_id=doc.patient_id,
        uploaded_by=doc.uploaded_by,
        doc_type=doc.doc_type,
        original_filename=doc.original_filename,
        display_name=doc.display_name,
        mime_type=doc.mime_type,
        file_size=doc.file_size,
        status=doc.status,
        error_message=doc.error_message,
        uploaded_at=doc.uploaded_at,
        confirmed_at=doc.confirmed_at,
        needs_review=doc.status == DocumentStatus.needs_review,
        retry_count=retry_count,
    )


def _to_status(doc: Document, retry_count: int = 0) -> DocumentStatusOut:
    base = _to_out(doc, retry_count)
    return DocumentStatusOut(
        **base.model_dump(),
        stage=STAGE_LABELS.get(doc.status, doc.status.value),
    )


async def create_upload_url(
    db: AsyncSession,
    user: User,
    data: UploadUrlRequest,
    *,
    ip_address: Optional[str] = None,
) -> UploadUrlResponse:
    if user.role != UserRole.patient:
        raise AppError("Only patients can upload documents", status_code=403)
    if get_settings().require_email_verification and not user.email_verified:
        raise AppError("Verify your email before uploading", status_code=403, code="email_unverified")
    await require_processing_consent(db, user)
    _validate_file(data.filename, data.mime_type, data.file_size)
    storage_service.require_storage()

    dup = await db.execute(
        select(Document).where(
            Document.patient_id == user.id,
            Document.file_hash == data.content_hash.lower(),
            Document.status != DocumentStatus.awaiting_upload,
        )
    )
    if dup.scalar_one_or_none():
        raise AppError(
            "This file was already uploaded",
            status_code=409,
            code="duplicate_file",
        )

    name = data.display_name.strip()
    if not name:
        raise AppError("display_name is required", status_code=400)
    doc_id = uuid.uuid4()
    object_id = uuid.uuid4()
    storage_key = f"{user.id}/{doc_id}/{object_id}"
    doc_type = _guess_doc_type(data.filename, data.mime_type, data.doc_type_hint)

    doc = Document(
        id=doc_id,
        patient_id=user.id,
        uploaded_by=user.id,
        doc_type=doc_type,
        storage_key=storage_key,
        original_filename=data.filename,
        display_name=name,
        mime_type=data.mime_type,
        file_size=data.file_size,
        file_hash=data.content_hash.lower(),
        status=DocumentStatus.awaiting_upload,
    )
    db.add(doc)
    await db.flush()

    await write_audit_log(
        db,
        actor_id=user.id,
        action="document.upload_url",
        resource_type="document",
        resource_id=str(doc.id),
        ip_address=ip_address,
        metadata={"filename": data.filename, "display_name": data.display_name, "mime_type": data.mime_type},
    )

    return UploadUrlResponse(
        document_id=doc.id,
        upload_url=f"/api/v1/documents/{doc.id}/content",
        auth_required=True,
        headers={"Content-Type": data.mime_type},
    )


async def store_uploaded_bytes(
    db: AsyncSession,
    user: User,
    document_id: UUID,
    data: bytes,
) -> None:
    doc = await _get_owned(db, user, document_id)
    if doc.status != DocumentStatus.awaiting_upload:
        raise AppError("Document is not awaiting upload", status_code=400)
    settings = get_settings()
    if len(data) > settings.max_upload_bytes:
        raise AppError("File is too large", status_code=413, code="file_too_large")
    if len(data) != doc.file_size:
        raise AppError(
            "Uploaded object size does not match the declared size",
            status_code=400,
            code="size_mismatch",
        )
    storage_service.put_object_bytes(doc.storage_key, data, doc.mime_type)
    doc.status = DocumentStatus.uploaded
    await db.flush()


async def complete_upload(
    db: AsyncSession,
    user: User,
    document_id: UUID,
    *,
    ip_address: Optional[str] = None,
) -> DocumentStatusOut:
    doc = await _get_owned(db, user, document_id)
    if doc.status not in (DocumentStatus.awaiting_upload, DocumentStatus.uploaded):
        raise AppError("Document is not awaiting completion", status_code=400)

    storage_service.require_storage()
    meta = storage_service.head_object(doc.storage_key)
    if meta["content_length"] != doc.file_size:
        storage_service.delete_object(doc.storage_key)
        raise AppError(
            "Uploaded object size does not match the declared size",
            status_code=400,
            code="size_mismatch",
        )
    stored_type = meta["content_type"].lower()
    expected_type = doc.mime_type.lower()
    if stored_type and stored_type != expected_type:
        storage_service.delete_object(doc.storage_key)
        raise AppError(
            "Uploaded object type does not match the declared type",
            status_code=400,
            code="type_mismatch",
        )

    try:
        file_bytes = storage_service.get_object_bytes(doc.storage_key)
    except AppError:
        storage_service.delete_object(doc.storage_key)
        raise

    digest = storage_service.sha256_hex(file_bytes)
    expected = (doc.file_hash or "").lower()
    if expected and digest != expected:
        storage_service.delete_object(doc.storage_key)
        raise AppError("Uploaded file does not match declared hash", status_code=400, code="hash_mismatch")

    other = await db.execute(
        select(Document).where(
            Document.patient_id == user.id,
            Document.file_hash == digest,
            Document.id != doc.id,
            Document.status != DocumentStatus.awaiting_upload,
        )
    )
    if other.scalar_one_or_none():
        storage_service.delete_object(doc.storage_key)
        raise AppError("This file was already uploaded", status_code=409, code="duplicate_file")

    doc.file_hash = digest
    doc.file_size = len(file_bytes)
    doc.status = DocumentStatus.pending
    doc.error_message = None
    await db.flush()

    job = IngestionJob(document_id=doc.id, status="pending")
    db.add(job)
    await db.flush()

    await write_audit_log(
        db,
        actor_id=user.id,
        action="document.uploaded",
        resource_type="document",
        resource_id=str(doc.id),
        ip_address=ip_address,
    )

    from app.workers.ingestion import enqueue_ingest

    enqueue_ingest(str(doc.id))
    await publish_document_status(doc.id, await _status_payload(db, doc))
    return _to_status(doc, 0)


async def get_status(db: AsyncSession, user: User, document_id: UUID) -> DocumentStatusOut:
    doc = await _get_accessible(db, user, document_id)
    job = await _latest_job(db, doc.id)
    return _to_status(doc, job.retry_count if job else 0)


async def list_documents(db: AsyncSession, user: User) -> list[DocumentOut]:
    if user.role == UserRole.patient:
        q = select(Document).where(Document.patient_id == user.id)
    elif user.role in (UserRole.doctor, UserRole.caregiver):
        from app.services.consent_service import granted_document_access

        full_patient_ids, document_ids = await granted_document_access(db, user)
        if not full_patient_ids and not document_ids:
            return []
        clauses = []
        if full_patient_ids:
            clauses.append(Document.patient_id.in_(full_patient_ids))
        if document_ids:
            clauses.append(Document.id.in_(document_ids))
        q = select(Document).where(or_(*clauses))
    else:
        raise AppError("Not authorized to list documents", status_code=403)

    result = await db.execute(
        q.where(Document.status != DocumentStatus.awaiting_upload).order_by(Document.uploaded_at.desc())
    )
    docs = list(result.scalars().all())
    outs: list[DocumentOut] = []
    for d in docs:
        job = await _latest_job(db, d.id)
        outs.append(_to_out(d, job.retry_count if job else 0))
    return outs


async def patch_document(
    db: AsyncSession, user: User, document_id: UUID, body: DocumentPatch
) -> DocumentOut:
    doc = await _get_owned(db, user, document_id)
    if body.doc_type is not None:
        doc.doc_type = body.doc_type
    if body.display_name is not None:
        doc.display_name = body.display_name.strip()
    await db.flush()
    job = await _latest_job(db, doc.id)
    return _to_out(doc, job.retry_count if job else 0)


async def get_extracted_fields(
    db: AsyncSession, user: User, document_id: UUID
) -> list[ExtractedFieldOut]:
    doc = await _get_accessible(db, user, document_id)
    result = await db.execute(
        select(ExtractedField)
        .where(ExtractedField.document_id == doc.id)
        .order_by(ExtractedField.name)
    )
    return [ExtractedFieldOut.model_validate(f) for f in result.scalars().all()]


async def save_extracted_fields(
    db: AsyncSession,
    user: User,
    document_id: UUID,
    fields: list[ExtractedFieldIn],
) -> list[ExtractedFieldOut]:
    doc = await _get_owned(db, user, document_id)
    existing = await db.execute(select(ExtractedField).where(ExtractedField.document_id == doc.id))
    for row in existing.scalars().all():
        await db.delete(row)
    await db.flush()
    for item in fields:
        db.add(
            ExtractedField(
                document_id=doc.id,
                field_type=item.field_type,
                name=item.name,
                value=item.value,
                unit=item.unit,
                reference_low=item.reference_low,
                reference_high=item.reference_high,
                observed_at=item.observed_at,
                source_confidence=item.source_confidence if item.source_confidence is not None else 1.0,
                canonical_code=item.canonical_code,
            )
        )
    await db.flush()
    return await get_extracted_fields(db, user, document_id)


async def confirm_document(
    db: AsyncSession, user: User, document_id: UUID, *, ip_address: Optional[str] = None
) -> DocumentStatusOut:
    doc = await _get_owned(db, user, document_id)
    if doc.status not in (
        DocumentStatus.needs_review,
        DocumentStatus.extracted,
        DocumentStatus.confirmed,
        DocumentStatus.validating,
    ):
        raise AppError("Document is not ready to confirm", status_code=400)
    doc.status = DocumentStatus.confirmed
    doc.confirmed_at = _utcnow()
    doc.error_message = None
    await db.flush()
    await write_audit_log(
        db,
        actor_id=user.id,
        action="document.confirmed",
        resource_type="document",
        resource_id=str(doc.id),
        ip_address=ip_address,
    )
    await publish_document_status(doc.id, await _status_payload(db, doc))
    job = await _latest_job(db, doc.id)
    return _to_status(doc, job.retry_count if job else 0)


async def retry_document(
    db: AsyncSession, user: User, document_id: UUID, *, ip_address: Optional[str] = None
) -> DocumentStatusOut:
    doc = await _get_owned(db, user, document_id)
    if doc.status not in (DocumentStatus.failed, DocumentStatus.retrying, DocumentStatus.needs_review):
        raise AppError("Only failed or reviewable documents can be retried", status_code=400)
    doc.status = DocumentStatus.pending
    doc.error_message = None
    job = await _latest_job(db, doc.id)
    if job:
        job.status = "retrying"
        job.retry_count += 1
        job.error_message = None
    else:
        job = IngestionJob(document_id=doc.id, status="retrying", retry_count=1)
        db.add(job)
    await db.flush()
    await write_audit_log(
        db,
        actor_id=user.id,
        action="document.retry",
        resource_type="document",
        resource_id=str(doc.id),
        ip_address=ip_address,
    )
    from app.workers.ingestion import enqueue_ingest

    enqueue_ingest(str(doc.id))
    await publish_document_status(doc.id, await _status_payload(db, doc))
    return _to_status(doc, job.retry_count)


async def get_file(
    db: AsyncSession, user: User, document_id: UUID, *, ip_address: Optional[str] = None
) -> tuple[bytes, str, str]:
    doc = await _get_accessible(db, user, document_id)
    if doc.status == DocumentStatus.awaiting_upload:
        raise AppError("File is not available yet", status_code=404)
    data = storage_service.get_object_bytes(doc.storage_key)
    mime_type = doc.mime_type
    filename = doc.original_filename
    if dicom_preview.is_dicom(mime_type, filename, data):
        data = dicom_preview.to_png_bytes(data)
        mime_type = "image/png"
        filename = dicom_preview.preview_filename(filename)
    await write_audit_log(
        db,
        actor_id=user.id,
        action="document.view",
        resource_type="document",
        resource_id=str(doc.id),
        ip_address=ip_address,
        metadata={"patient_id": str(doc.patient_id)},
    )
    return data, mime_type, filename


async def document_counts(db: AsyncSession, user: User) -> dict:
    if user.role != UserRole.patient:
        return {"total": 0, "last_uploaded_at": None}
    result = await db.execute(
        select(func.count(Document.id), func.max(Document.uploaded_at)).where(
            Document.patient_id == user.id,
            Document.status != DocumentStatus.awaiting_upload,
        )
    )
    total, last = result.one()
    return {"total": int(total or 0), "last_uploaded_at": last}


async def _get_owned(db: AsyncSession, user: User, document_id: UUID) -> Document:
    doc = await db.get(Document, document_id)
    if not doc:
        raise AppError("Document not found", status_code=404)
    if doc.patient_id != user.id and doc.uploaded_by != user.id:
        raise AppError("Document not found", status_code=404)
    return doc


async def _get_accessible(db: AsyncSession, user: User, document_id: UUID) -> Document:
    doc = await db.get(Document, document_id)
    if not doc:
        raise AppError("Document not found", status_code=404)
    ok = await can_access_document(db, actor=user, document=doc)
    if not ok:
        raise AppError("Document not found", status_code=404)
    return doc
