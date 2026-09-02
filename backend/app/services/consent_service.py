from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.document import DocType, Document, DocumentStatus
from app.models.user import (
    ConsentGrant,
    ConsentScope,
    DoctorProfile,
    User,
    UserRole,
    UserStatus,
)
from app.schemas.auth import ConsentGrantCreate, ConsentGrantOut, VerifiedDoctorOut
from app.services.audit_service import write_audit_log

DOC_TYPE_LABELS = {
    DocType.blood_test: "Blood test",
    DocType.prescription: "Prescription",
    DocType.mri: "MRI",
    DocType.ct: "CT",
    DocType.discharge: "Discharge summary",
    DocType.other: "Other",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _is_active_grant(grant: ConsentGrant) -> bool:
    if grant.revoked_at is not None:
        return False
    if grant.expires_at is not None:
        exp = grant.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp < _utcnow():
            return False
    return True


def _grant_document_id(grant: ConsentGrant) -> Optional[UUID]:
    if grant.scope != ConsentScope.document or not grant.scope_detail:
        return None
    raw = grant.scope_detail.get("document_id")
    if not raw:
        return None
    try:
        return UUID(str(raw))
    except ValueError:
        return None


def _document_preview(doc: Optional[Document]) -> dict:
    if not doc:
        return {"label": "Document (removed)", "includes": []}
    name = (doc.display_name or "").strip() or doc.original_filename
    date = ""
    if doc.uploaded_at:
        date = doc.uploaded_at.strftime("%d %b %Y").lstrip("0")
    label = f"{name} · {date}" if date else name
    includes = [DOC_TYPE_LABELS.get(doc.doc_type, doc.doc_type.value)]
    return {"label": label, "includes": includes}


async def _preview_for_grant(db: AsyncSession, grant: ConsentGrant) -> dict:
    if grant.scope == ConsentScope.document:
        doc_id = _grant_document_id(grant)
        doc = await db.get(Document, doc_id) if doc_id else None
        return _document_preview(doc)
    return _scope_preview(grant.scope)


async def active_grant_exists(
    db: AsyncSession,
    *,
    grantee_id: UUID,
    patient_id: UUID,
    required_scope: Optional[ConsentScope] = None,
) -> bool:
    """Resource-level consent check — role alone is never sufficient."""
    result = await db.execute(
        select(ConsentGrant).where(
            ConsentGrant.patient_id == patient_id,
            ConsentGrant.grantee_id == grantee_id,
            ConsentGrant.revoked_at.is_(None),
        )
    )
    for grant in result.scalars().all():
        if not _is_active_grant(grant):
            continue
        if required_scope is None or grant.scope == ConsentScope.all or grant.scope == required_scope:
            return True
    return False


async def can_access_patient(
    db: AsyncSession,
    *,
    actor: User,
    patient_id: UUID,
    required_scope: Optional[ConsentScope] = None,
) -> bool:
    if actor.id == patient_id:
        return True
    if actor.role == UserRole.admin:
        # Admin has no clinical data access by default
        return False
    if actor.role in (UserRole.doctor, UserRole.caregiver):
        return await active_grant_exists(
            db,
            grantee_id=actor.id,
            patient_id=patient_id,
            required_scope=required_scope,
        )
    return False


async def can_access_document(
    db: AsyncSession, *, actor: User, document: Document
) -> bool:
    if actor.id == document.patient_id:
        return True
    if actor.role == UserRole.admin:
        return False
    if actor.role not in (UserRole.doctor, UserRole.caregiver):
        return False
    result = await db.execute(
        select(ConsentGrant).where(
            ConsentGrant.patient_id == document.patient_id,
            ConsentGrant.grantee_id == actor.id,
            ConsentGrant.revoked_at.is_(None),
        )
    )
    for grant in result.scalars().all():
        if not _is_active_grant(grant):
            continue
        if grant.scope == ConsentScope.document:
            if _grant_document_id(grant) == document.id:
                return True
            continue
        return True
    return False


async def granted_document_access(
    db: AsyncSession, grantee: User
) -> tuple[list[UUID], list[UUID]]:
    """Patient IDs with full (legacy) access, plus specific granted document IDs."""
    result = await db.execute(
        select(ConsentGrant).where(
            ConsentGrant.grantee_id == grantee.id,
            ConsentGrant.revoked_at.is_(None),
        )
    )
    full_patient_ids: set[UUID] = set()
    document_ids: set[UUID] = set()
    for grant in result.scalars().all():
        if not _is_active_grant(grant):
            continue
        if grant.scope == ConsentScope.document:
            doc_id = _grant_document_id(grant)
            if doc_id:
                document_ids.add(doc_id)
        else:
            full_patient_ids.add(grant.patient_id)
    return list(full_patient_ids), list(document_ids)


async def list_verified_doctors(db: AsyncSession) -> list[VerifiedDoctorOut]:
    result = await db.execute(
        select(User, DoctorProfile)
        .join(DoctorProfile, DoctorProfile.user_id == User.id)
        .where(
            User.role == UserRole.doctor,
            User.status == UserStatus.active,
            DoctorProfile.verified_at.is_not(None),
        )
        .order_by(User.full_name.asc())
    )
    doctors: list[VerifiedDoctorOut] = []
    for user, profile in result.all():
        doctors.append(
            VerifiedDoctorOut(
                id=user.id,
                full_name=user.full_name,
                bmdc_registration_number=profile.bmdc_registration_number if profile else None,
                specialty=profile.specialty if profile else None,
            )
        )
    return doctors


async def create_grant(
    db: AsyncSession,
    patient: User,
    data: ConsentGrantCreate,
    *,
    ip_address: Optional[str] = None,
) -> ConsentGrantOut:
    if patient.role != UserRole.patient:
        raise AppError("Only patients can grant consent", status_code=403)

    grantee = await db.get(User, data.grantee_id)
    if not grantee:
        raise AppError("Grantee not found", status_code=404)
    if grantee.role not in (UserRole.doctor, UserRole.caregiver):
        raise AppError("Grantee must be a doctor or caregiver", status_code=400)
    if grantee.role == UserRole.doctor:
        profile = await db.get(DoctorProfile, grantee.id)
        if grantee.status != UserStatus.active or not profile or not profile.verified_at:
            raise AppError(
                "Doctor must be verified before receiving consent grants",
                status_code=400,
                code="doctor_unverified",
            )

    doc: Optional[Document] = None
    scope_detail = data.scope_detail
    if data.scope == ConsentScope.document:
        raw = (scope_detail or {}).get("document_id")
        if not raw:
            raise AppError("document_id is required", status_code=400)
        try:
            doc_id = UUID(str(raw))
        except ValueError as exc:
            raise AppError("Invalid document_id", status_code=400) from exc
        doc = await db.get(Document, doc_id)
        if not doc or doc.patient_id != patient.id:
            raise AppError("Document not found", status_code=404)
        if doc.status in (DocumentStatus.awaiting_upload, DocumentStatus.failed):
            raise AppError("This document cannot be shared yet", status_code=400)
        scope_detail = {"document_id": str(doc.id)}
        existing = await db.execute(
            select(ConsentGrant).where(
                ConsentGrant.patient_id == patient.id,
                ConsentGrant.grantee_id == data.grantee_id,
                ConsentGrant.scope == ConsentScope.document,
                ConsentGrant.revoked_at.is_(None),
            )
        )
        for grant in existing.scalars().all():
            if not _is_active_grant(grant):
                continue
            if _grant_document_id(grant) == doc.id:
                raise AppError(
                    "This doctor already has access to that document",
                    status_code=409,
                    code="duplicate_grant",
                )

    grant = ConsentGrant(
        patient_id=patient.id,
        grantee_id=data.grantee_id,
        scope=data.scope,
        scope_detail=scope_detail,
        expires_at=data.expires_at,
    )
    db.add(grant)
    await db.flush()

    await write_audit_log(
        db,
        actor_id=patient.id,
        action="consent.grant",
        resource_type="consent_grant",
        resource_id=str(grant.id),
        ip_address=ip_address,
        metadata={
            "grantee_id": str(data.grantee_id),
            "scope": data.scope.value,
            "document_id": str(doc.id) if doc else None,
        },
    )

    preview = _document_preview(doc) if doc else _scope_preview(data.scope)
    return _to_out(
        grant,
        grantee_name=grantee.full_name,
        patient_name=patient.full_name,
        preview=preview,
    )


async def revoke_grant(
    db: AsyncSession,
    patient: User,
    grant_id: UUID,
    *,
    ip_address: Optional[str] = None,
) -> None:
    grant = await db.get(ConsentGrant, grant_id)
    if not grant or grant.patient_id != patient.id:
        raise AppError("Grant not found", status_code=404)
    if grant.revoked_at is not None:
        raise AppError("Grant already revoked", status_code=400)

    grant.revoked_at = _utcnow()
    await db.flush()
    # Immediate invalidation — no cache TTL reliance
    await write_audit_log(
        db,
        actor_id=patient.id,
        action="consent.revoke",
        resource_type="consent_grant",
        resource_id=str(grant.id),
        ip_address=ip_address,
        metadata={"grantee_id": str(grant.grantee_id)},
    )


async def list_grants(
    db: AsyncSession,
    user: User,
    *,
    include_revoked: bool = False,
) -> list[ConsentGrantOut]:
    if user.role == UserRole.patient:
        q = select(ConsentGrant).where(ConsentGrant.patient_id == user.id)
    elif user.role in (UserRole.doctor, UserRole.caregiver):
        q = select(ConsentGrant).where(ConsentGrant.grantee_id == user.id)
    else:
        raise AppError("Not authorized to list consent grants", status_code=403)

    if not include_revoked:
        q = q.where(ConsentGrant.revoked_at.is_(None))

    result = await db.execute(q.order_by(ConsentGrant.granted_at.desc()))
    grants = list(result.scalars().all())

    outs: list[ConsentGrantOut] = []
    for g in grants:
        patient = await db.get(User, g.patient_id)
        grantee = await db.get(User, g.grantee_id)
        outs.append(
            _to_out(
                g,
                patient_name=patient.full_name if patient else None,
                grantee_name=grantee.full_name if grantee else None,
                preview=await _preview_for_grant(db, g),
            )
        )
    return outs


def _scope_preview(scope: ConsentScope) -> dict:
    """What the doctor will see — shown to patient before confirming grant."""
    previews = {
        ConsentScope.all: {
            "label": "All health records",
            "includes": [
                "Lab results and trends",
                "Imaging studies and findings",
                "Prescriptions and medications",
                "Discharge summaries",
                "AI summaries and alerts",
            ],
        },
        ConsentScope.labs: {
            "label": "Lab results only",
            "includes": ["Lab results and trends", "Related abnormal-value alerts"],
        },
        ConsentScope.imaging: {
            "label": "Imaging only",
            "includes": ["MRI/CT studies", "Imaging findings text"],
        },
        ConsentScope.prescriptions: {
            "label": "Prescriptions only",
            "includes": ["Medication names, dosages, and frequency"],
        },
        ConsentScope.discharge: {
            "label": "Discharge summaries only",
            "includes": ["Diagnoses, procedures, follow-up instructions"],
        },
    }
    return previews.get(scope, {"label": scope.value, "includes": []})


def _to_out(
    grant: ConsentGrant,
    *,
    grantee_name: Optional[str] = None,
    patient_name: Optional[str] = None,
    preview: Optional[dict] = None,
) -> ConsentGrantOut:
    return ConsentGrantOut(
        id=grant.id,
        patient_id=grant.patient_id,
        grantee_id=grant.grantee_id,
        scope=grant.scope,
        scope_detail=grant.scope_detail,
        expires_at=grant.expires_at,
        granted_at=grant.granted_at,
        revoked_at=grant.revoked_at,
        grantee_name=grantee_name,
        patient_name=patient_name,
        preview=preview,
    )
