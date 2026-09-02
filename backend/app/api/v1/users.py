from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import client_ip, get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import MessageOut
from app.services import account_service

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me/export")
async def export_me(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> JSONResponse:
    payload: dict[str, Any] = await account_service.export_account(
        db, user, ip_address=client_ip(request)
    )
    return JSONResponse(
        payload,
        headers={"Content-Disposition": 'attachment; filename="spondon-export.json"'},
    )


@router.delete("/me", response_model=MessageOut)
async def delete_me(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> MessageOut:
    await account_service.delete_account(db, user, ip_address=client_ip(request))
    return MessageOut(message="Account deleted.")
