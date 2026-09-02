from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import get_redis, status_channel
from app.core.security import decode_token
from app.db.session import get_db
from app.models.document import Document
from app.models.user import User, UserStatus
from app.services.auth_service import get_user_by_id
from app.services.consent_service import can_access_document
from app.services.document_service import get_status

router = APIRouter(tags=["documents"])


async def _user_from_token(db: AsyncSession, token: str | None) -> User | None:
    if not token:
        return None
    try:
        payload = decode_token(token)
    except JWTError:
        return None
    if payload.get("type") != "access":
        return None
    sub = payload.get("sub")
    if not sub:
        return None
    user = await get_user_by_id(db, UUID(sub))
    if not user or user.status == UserStatus.suspended:
        return None
    return user


@router.websocket("/ws/documents/{document_id}/status")
async def document_status_ws(
    websocket: WebSocket,
    document_id: UUID,
) -> None:
    await websocket.accept()
    token = websocket.query_params.get("token")
    async for db in get_db():
        user = await _user_from_token(db, token)
        if not user:
            await websocket.close(code=4401)
            return
        doc = await db.get(Document, document_id)
        if not doc or not await can_access_document(db, actor=user, document=doc):
            await websocket.close(code=4403)
            return
        current = await get_status(db, user, document_id)
        await websocket.send_json(current.model_dump(mode="json"))
        break

    redis = get_redis()
    pubsub = redis.pubsub()
    try:
        await pubsub.subscribe(status_channel(document_id))
        async for message in pubsub.listen():
            if message.get("type") != "message":
                continue
            data = message.get("data")
            if isinstance(data, bytes):
                data = data.decode()
            await websocket.send_text(data)
    except WebSocketDisconnect:
        pass
    except Exception:
        await websocket.close()
    finally:
        await pubsub.unsubscribe(status_channel(document_id))
        await pubsub.aclose()
