from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.user import (
    ConsentGrant,
    ConsentScope,
    User,
    UserRole,
    UserStatus,
)
from app.schemas.auth import ConsentGrantCreate, ConsentGrantOut
from app.services.audit_service import write_audit_log


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
    if grantee.role == UserRole.doctor and grantee.status != UserStatus.active:
        raise AppError(
            "Doctor must be verified before receiving consent grants",
            status_code=400,
            code="doctor_unverified",
        )

    grant = ConsentGrant(
        patient_id=patient.id,
        grantee_id=data.grantee_id,
        scope=data.scope,
        scope_detail=data.scope_detail,
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
        metadata={"grantee_id": str(data.grantee_id), "scope": data.scope.value},
    )

    return _to_out(
        grant,
        grantee_name=grantee.full_name,
        patient_name=patient.full_name,
        preview=_scope_preview(data.scope),
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
                preview=_scope_preview(g.scope) if user.role == UserRole.patient else None,
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
