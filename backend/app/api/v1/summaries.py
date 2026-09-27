from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import client_ip, get_current_user, require_role
from app.db.session import get_db
from app.models.summary import SummaryAudience
from app.models.user import User
from app.schemas.summaries import SummaryOut, SummaryVersionOut
from app.services import summary_service

router = APIRouter(prefix="/summaries", tags=["summaries"])


@router.get("/{document_id}", response_model=SummaryOut)
async def get_summary(
    document_id: UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    audience: SummaryAudience = SummaryAudience.patient,
    version: Optional[int] = Query(None, ge=1),
) -> SummaryOut:
    summary = await summary_service.get_summary(
        db, user, document_id, audience, version=version, ip_address=client_ip(request)
    )
    if summary is None:
        return SummaryOut(status="pending", document_id=document_id, audience=audience)
    return SummaryOut.model_validate(summary)


@router.get("/{document_id}/versions", response_model=list[SummaryVersionOut])
async def list_versions(
    document_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> list[SummaryVersionOut]:
    rows = await summary_service.list_versions(db, user, document_id)
    return [SummaryVersionOut.model_validate(r) for r in rows]


@router.post("/{document_id}/regenerate", status_code=status.HTTP_202_ACCEPTED)
async def regenerate(
    document_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_role(["patient"]))],
) -> dict[str, str]:
    document = await summary_service.request_regeneration(db, user, document_id)
    from app.workers.ingestion import enqueue_analysis

    enqueue_analysis(str(document.id))
    return {"status": "queued"}
