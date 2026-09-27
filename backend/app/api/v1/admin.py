from datetime import datetime
from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    approve_doctor,
    client_ip,
    list_users_admin,
    pipeline_health,
    query_audit_logs,
    reject_doctor,
    require_role,
)
from app.db.session import get_db
from app.models.user import User, UserRole, UserStatus
from app.schemas.auth import AdminUserOut, AuditLogOut, MessageOut, PipelineHealthOut

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users", response_model=list[AdminUserOut])
async def list_users(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(require_role(["admin"]))],
    role: Optional[UserRole] = None,
    status: Optional[UserStatus] = None,
    limit: int = Query(200, ge=1, le=500),
) -> list[AdminUserOut]:
    return await list_users_admin(db, role=role, status=status, limit=limit)


@router.post("/users/{user_id}/approve-doctor", response_model=AdminUserOut)
async def approve_doctor_endpoint(
    user_id: UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[User, Depends(require_role(["admin"]))],
) -> AdminUserOut:
    return await approve_doctor(db, admin, user_id, ip_address=client_ip(request))


@router.post("/users/{user_id}/reject-doctor", response_model=AdminUserOut)
async def reject_doctor_endpoint(
    user_id: UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[User, Depends(require_role(["admin"]))],
) -> AdminUserOut:
    return await reject_doctor(db, admin, user_id, ip_address=client_ip(request))


@router.get("/audit-logs", response_model=list[AuditLogOut])
async def audit_logs(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(require_role(["admin"]))],
    actor: Optional[UUID] = None,
    resource: Optional[str] = None,
    from_: Optional[datetime] = Query(None, alias="from"),
    to: Optional[datetime] = None,
) -> list[AuditLogOut]:
    # Metadata only — never clinical field values
    return await query_audit_logs(
        db, actor=actor, resource=resource, from_dt=from_, to_dt=to
    )


@router.get("/pipeline-health", response_model=PipelineHealthOut)
async def get_pipeline_health(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(require_role(["admin"]))],
) -> PipelineHealthOut:
    return await pipeline_health(db)
