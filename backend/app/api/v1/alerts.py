from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import client_ip, get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.alerts import AcknowledgeAllOut, AlertOut, UnreadCountOut
from app.services import alert_service

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("", response_model=list[AlertOut])
async def list_alerts(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    unacknowledged_only: bool = False,
    limit: int = Query(50, ge=1, le=200),
) -> list[AlertOut]:
    alerts = await alert_service.list_alerts(
        db, user, unacknowledged_only=unacknowledged_only, limit=limit
    )
    rows = await alert_service.to_out_rows(db, alerts)
    return [AlertOut(**row) for row in rows]


@router.get("/unread-count", response_model=UnreadCountOut)
async def unread_count(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> UnreadCountOut:
    return UnreadCountOut(count=await alert_service.unread_count(db, user))


@router.patch("/{alert_id}/acknowledge", response_model=AlertOut)
async def acknowledge(
    alert_id: UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> AlertOut:
    alert = await alert_service.acknowledge(db, user, alert_id, ip_address=client_ip(request))
    row = (await alert_service.to_out_rows(db, [alert]))[0]
    return AlertOut(**row)


@router.post("/acknowledge-all", response_model=AcknowledgeAllOut)
async def acknowledge_all(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> AcknowledgeAllOut:
    count = await alert_service.acknowledge_all(db, user, ip_address=client_ip(request))
    return AcknowledgeAllOut(acknowledged=count)
