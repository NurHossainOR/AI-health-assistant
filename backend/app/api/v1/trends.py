from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import client_ip, get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.trends import CompareOut, TrendMetricOut, TrendsOut
from app.services import trend_service

router = APIRouter(prefix="/trends", tags=["trends"])


@router.get("/metrics", response_model=list[TrendMetricOut])
async def list_metrics(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    patient_id: Optional[UUID] = None,
) -> list[TrendMetricOut]:
    rows = await trend_service.list_metrics(db, user, patient_id, ip_address=client_ip(request))
    return [TrendMetricOut(**row) for row in rows]


@router.get("/compare", response_model=CompareOut)
async def compare(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    document_id: UUID,
    against: Optional[UUID] = None,
) -> CompareOut:
    result = await trend_service.compare_document(
        db, user, document_id, against=against, ip_address=client_ip(request)
    )
    return CompareOut(**result)


@router.get("", response_model=TrendsOut)
async def get_trends(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    patient_id: Optional[UUID] = None,
    metrics: Optional[str] = Query(None, description="Comma-separated metric keys"),
    range: str = Query("all", pattern="^(1m|3m|6m|1y|2y|5y|all)$"),
) -> TrendsOut:
    keys = [m for m in (metrics or "").split(",") if m.strip()]
    result = await trend_service.get_trends(
        db, user, patient_id, metrics=keys, range_key=range, ip_address=client_ip(request)
    )
    return TrendsOut(**result)
