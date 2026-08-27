from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import client_ip, get_current_user, require_role
from app.db.session import get_db
from app.models.user import User, UserRole
from app.schemas.auth import ConsentGrantCreate, ConsentGrantOut, MessageOut
from app.services import consent_service

router = APIRouter(prefix="/consent", tags=["consent"])


@router.post("/grants", response_model=ConsentGrantOut)
async def create_grant(
    body: ConsentGrantCreate,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_role(["patient"]))],
) -> ConsentGrantOut:
    return await consent_service.create_grant(
        db, user, body, ip_address=client_ip(request)
    )


@router.delete("/grants/{grant_id}", response_model=MessageOut)
async def revoke_grant(
    grant_id: UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_role(["patient"]))],
) -> MessageOut:
    await consent_service.revoke_grant(
        db, user, grant_id, ip_address=client_ip(request)
    )
    return MessageOut(message="Consent grant revoked.")


@router.get("/grants", response_model=list[ConsentGrantOut])
async def list_grants(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_role(["patient", "doctor", "caregiver"]))],
    include_revoked: bool = Query(False),
) -> list[ConsentGrantOut]:
    return await consent_service.list_grants(db, user, include_revoked=include_revoked)
