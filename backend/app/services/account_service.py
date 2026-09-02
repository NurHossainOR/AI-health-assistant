from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import AppError
from app.models.document import Document
from app.models.user import ConsentGrant, PatientProfile, RefreshToken, User, UserRole
from app.schemas.documents import ProcessingConsentOut
from app.services import storage_service
from app.services.audit_service import write_audit_log


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def get_processing_consent(db: AsyncSession, user: User) -> ProcessingConsentOut:
    if user.role != UserRole.patient:
        return ProcessingConsentOut(granted=True, granted_at=user.created_at)
    profile = await db.get(PatientProfile, user.id)
    granted_at = profile.processing_consent_at if profile else None
    return ProcessingConsentOut(granted=granted_at is not None, granted_at=granted_at)


async def grant_processing_consent(
    db: AsyncSession, user: User, *, ip_address: Optional[str] = None
) -> ProcessingConsentOut:
    if user.role != UserRole.patient:
        raise AppError("Only patients grant processing consent", status_code=403)
    profile = await db.get(PatientProfile, user.id)
    if not profile:
        profile = PatientProfile(user_id=user.id)
        db.add(profile)
        await db.flush()
    if profile.processing_consent_at is None:
        profile.processing_consent_at = _utcnow()
        await write_audit_log(
            db,
            actor_id=user.id,
            action="consent.processing_granted",
            resource_type="user",
            resource_id=str(user.id),
            ip_address=ip_address,
        )
    return ProcessingConsentOut(granted=True, granted_at=profile.processing_consent_at)


async def export_account(db: AsyncSession, user: User, *, ip_address: Optional[str] = None) -> dict[str, Any]:
    await write_audit_log(
        db,
        actor_id=user.id,
        action="user.data_export",
        resource_type="user",
        resource_id=str(user.id),
        ip_address=ip_address,
    )
    profile = await db.get(PatientProfile, user.id)
    grants = await db.execute(
        select(ConsentGrant).where(
            (ConsentGrant.patient_id == user.id) | (ConsentGrant.grantee_id == user.id)
        )
    )
    docs_q = await db.execute(
        select(Document)
        .options(selectinload(Document.pages), selectinload(Document.extracted_fields))
        .where(Document.patient_id == user.id)
    )
    documents = []
    for doc in docs_q.scalars().all():
        documents.append(
            {
                "id": str(doc.id),
                "doc_type": doc.doc_type.value,
                "original_filename": doc.original_filename,
                "display_name": doc.display_name,
                "status": doc.status.value,
                "uploaded_at": doc.uploaded_at.isoformat() if doc.uploaded_at else None,
                "confirmed_at": doc.confirmed_at.isoformat() if doc.confirmed_at else None,
                "pages": [
                    {"page_number": p.page_number, "ocr_text": p.ocr_text, "ocr_confidence": p.ocr_confidence}
                    for p in doc.pages
                ],
                "extracted_fields": [
                    {
                        "name": f.name,
                        "value": f.value,
                        "unit": f.unit,
                        "reference_low": f.reference_low,
                        "reference_high": f.reference_high,
                        "source_confidence": f.source_confidence,
                    }
                    for f in doc.extracted_fields
                ],
            }
        )
    return {
        "exported_at": _utcnow().isoformat(),
        "user": {
            "id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role.value,
            "status": user.status.value,
            "created_at": user.created_at.isoformat() if user.created_at else None,
        },
        "profile": {
            "date_of_birth": profile.date_of_birth.isoformat() if profile and profile.date_of_birth else None,
            "sex": profile.sex if profile else None,
            "allergies": profile.allergies if profile else None,
            "processing_consent_at": profile.processing_consent_at.isoformat()
            if profile and profile.processing_consent_at
            else None,
        }
        if user.role == UserRole.patient
        else None,
        "consent_grants": [
            {
                "id": str(g.id),
                "patient_id": str(g.patient_id),
                "grantee_id": str(g.grantee_id),
                "scope": g.scope.value,
                "granted_at": g.granted_at.isoformat() if g.granted_at else None,
                "revoked_at": g.revoked_at.isoformat() if g.revoked_at else None,
            }
            for g in grants.scalars().all()
        ],
        "documents": documents,
    }


async def delete_account(db: AsyncSession, user: User, *, ip_address: Optional[str] = None) -> None:
    await write_audit_log(
        db,
        actor_id=user.id,
        action="user.account_deleted",
        resource_type="user",
        resource_id=str(user.id),
        ip_address=ip_address,
        metadata={"email": user.email},
    )
    docs = await db.execute(select(Document).where(Document.patient_id == user.id))
    for doc in docs.scalars().all():
        storage_service.delete_object(doc.storage_key)

    tokens = await db.execute(select(RefreshToken).where(RefreshToken.user_id == user.id))
    now = _utcnow()
    for t in tokens.scalars().all():
        t.revoked_at = now

    await db.delete(user)
    await db.flush()
