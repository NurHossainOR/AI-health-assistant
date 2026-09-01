from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Callable, Optional, Sequence
from uuid import UUID

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import raise_forbidden, raise_unauthorized
from app.core.security import decode_token
from app.db.session import get_db
from app.models.user import AuditLog, DoctorProfile, IngestionJob, User, UserRole, UserStatus
from app.schemas.auth import AdminUserOut, AuditLogOut, PipelineHealthOut, UserOut
from app.services.audit_service import write_audit_log
from app.services.auth_service import get_user_by_id

bearer_scheme = HTTPBearer(auto_error=False)


def client_ip(request: Request) -> Optional[str]:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


async def get_current_user_optional(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(bearer_scheme)],
) -> Optional[User]:
    if not credentials or credentials.scheme.lower() != "bearer":
        return None
    try:
        payload = decode_token(credentials.credentials)
    except JWTError:
        return None
    if payload.get("type") != "access":
        return None
    user_id = payload.get("sub")
    if not user_id:
        return None
    user = await get_user_by_id(db, UUID(user_id))
    if not user or user.status == UserStatus.suspended:
        return None
    request.state.user = user
    return user


async def get_current_user(
    user: Annotated[Optional[User], Depends(get_current_user_optional)],
) -> User:
    if not user:
        raise_unauthorized()
    return user


def require_role(allowed: Sequence[str | UserRole]) -> Callable:
    allowed_set = {a.value if isinstance(a, UserRole) else a for a in allowed}

    async def _dependency(user: Annotated[User, Depends(get_current_user)]) -> User:
        if user.role.value not in allowed_set:
            raise_forbidden(f"Requires one of roles: {sorted(allowed_set)}")
        return user

    return _dependency


async def audit_phi_access(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> None:
    """
    Shared dependency for PHI routes: logs access after the route sets
    request.state.audit_resource = {type, id, action}.
    Prefer calling write_audit_log explicitly in services; this is a safety net.
    """
    # Middleware-style: log on exit via background — for simplicity log a generic access
    # Routes should set request.state.audit before returning.
    yield
    info = getattr(request.state, "audit_resource", None)
    if info:
        await write_audit_log(
            db,
            actor_id=user.id,
            action=info.get("action", f"{request.method.lower()}.access"),
            resource_type=info["type"],
            resource_id=str(info.get("id", "")),
            ip_address=client_ip(request),
            metadata=info.get("metadata"),
        )


# --- Admin helpers ---


async def list_users_admin(
    db: AsyncSession,
    *,
    role: Optional[UserRole] = None,
    status: Optional[UserStatus] = None,
) -> list[AdminUserOut]:
    q = select(User)
    if role:
        q = q.where(User.role == role)
    if status:
        q = q.where(User.status == status)
    result = await db.execute(q.order_by(User.created_at.desc()))
    users = result.scalars().all()
    outs: list[AdminUserOut] = []
    for u in users:
        npi = specialty = verified_at = None
        if u.role == UserRole.doctor:
            dp = await db.get(DoctorProfile, u.id)
            if dp:
                npi, specialty, verified_at = dp.bmdc_registration_number, dp.specialty, dp.verified_at
        base = UserOut.model_validate(u)
        outs.append(
            AdminUserOut(
                **base.model_dump(),
                bmdc_registration_number=npi,
                specialty=specialty,
                verified_at=verified_at,
            )
        )
    return outs


async def approve_doctor(
    db: AsyncSession,
    admin: User,
    doctor_id: UUID,
    *,
    ip_address: Optional[str] = None,
) -> AdminUserOut:
    doctor = await get_user_by_id(db, doctor_id)
    if not doctor or doctor.role != UserRole.doctor:
        raise_forbidden("Not a doctor account")

    doctor.status = UserStatus.active
    doctor.email_verified = True
    profile = await db.get(DoctorProfile, doctor.id)
    if profile:
        profile.verified_at = datetime.now(timezone.utc)
        profile.verified_by = admin.id
    await db.flush()
    await write_audit_log(
        db,
        actor_id=admin.id,
        action="admin.doctor_approved",
        resource_type="user",
        resource_id=str(doctor.id),
        ip_address=ip_address,
        metadata={"npi": profile.bmdc_registration_number if profile else None},
    )
    base = UserOut.model_validate(doctor)
    return AdminUserOut(
        **base.model_dump(),
        bmdc_registration_number=profile.bmdc_registration_number if profile else None,
        specialty=profile.specialty if profile else None,
        verified_at=profile.verified_at if profile else None,
    )


async def query_audit_logs(
    db: AsyncSession,
    *,
    actor: Optional[UUID] = None,
    resource: Optional[str] = None,
    from_dt: Optional[datetime] = None,
    to_dt: Optional[datetime] = None,
    limit: int = 100,
) -> list[AuditLogOut]:
    q = select(AuditLog)
    if actor:
        q = q.where(AuditLog.actor_id == actor)
    if resource:
        q = q.where(AuditLog.resource_type == resource)
    if from_dt:
        q = q.where(AuditLog.created_at >= from_dt)
    if to_dt:
        q = q.where(AuditLog.created_at <= to_dt)
    q = q.order_by(AuditLog.created_at.desc()).limit(min(limit, 500))
    result = await db.execute(q)
    return [AuditLogOut.model_validate(row) for row in result.scalars().all()]


async def pipeline_health(db: AsyncSession) -> PipelineHealthOut:
    result = await db.execute(
        select(IngestionJob.status, func.count()).group_by(IngestionJob.status)
    )
    counts = {status: count for status, count in result.all()}
    failures = await db.execute(
        select(IngestionJob)
        .where(IngestionJob.status.in_(["failed", "retrying"]))
        .order_by(IngestionJob.updated_at.desc())
        .limit(20)
    )
    recent = [
        {
            "id": str(j.id),
            "document_id": str(j.document_id) if j.document_id else None,
            "status": j.status,
            "error_message": j.error_message,
            "retry_count": j.retry_count,
            "updated_at": j.updated_at.isoformat() if j.updated_at else None,
        }
        for j in failures.scalars().all()
    ]
    total = sum(counts.values())
    return PipelineHealthOut(
        total=total,
        pending=counts.get("pending", 0),
        running=counts.get("running", 0),
        succeeded=counts.get("succeeded", 0),
        failed=counts.get("failed", 0),
        retrying=counts.get("retrying", 0),
        recent_failures=recent,
    )
