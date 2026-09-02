from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import client_ip, get_current_user, require_role
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import ConsentGrantCreate, ConsentGrantOut, MessageOut, VerifiedDoctorOut
from app.schemas.documents import ProcessingConsentOut
from app.services import account_service, consent_service

router = APIRouter(prefix="/consent", tags=["consent"])


@router.get("/processing", response_model=ProcessingConsentOut)
async def get_processing_consent(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> ProcessingConsentOut:
    return await account_service.get_processing_consent(db, user)


@router.post("/processing", response_model=ProcessingConsentOut)
async def grant_processing_consent(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_role(["patient"]))],
) -> ProcessingConsentOut:
    return await account_service.grant_processing_consent(
        db, user, ip_address=client_ip(request)
    )


@router.get("/doctors", response_model=list[VerifiedDoctorOut])
async def list_verified_doctors(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(require_role(["patient"]))],
) -> list[VerifiedDoctorOut]:
    return await consent_service.list_verified_doctors(db)


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
