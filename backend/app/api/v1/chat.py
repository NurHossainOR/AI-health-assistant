from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import client_ip, require_role
from app.db.session import AsyncSessionLocal, get_db
from app.models.user import User
from app.schemas.chat import ChatMessageIn, ChatMessageOut, ChatSessionCreate, ChatSessionOut
from app.services import rag_service

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/sessions", response_model=ChatSessionOut)
async def create_session(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_role(["patient"]))],
    body: ChatSessionCreate = ChatSessionCreate(),
) -> ChatSessionOut:
    session = await rag_service.create_session(db, user, body.title)
    return ChatSessionOut.model_validate(session)


@router.get("/sessions", response_model=list[ChatSessionOut])
async def list_sessions(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_role(["patient"]))],
    limit: int = Query(50, ge=1, le=200),
) -> list[ChatSessionOut]:
    sessions = await rag_service.list_sessions(db, user, limit=limit)
    return [ChatSessionOut.model_validate(s) for s in sessions]


@router.get("/sessions/{session_id}/messages", response_model=list[ChatMessageOut])
async def list_messages(
    session_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_role(["patient"]))],
    limit: int = Query(200, ge=1, le=500),
) -> list[ChatMessageOut]:
    messages = await rag_service.list_messages(db, user, session_id, limit=limit)
    return [ChatMessageOut.model_validate(m) for m in messages]


@router.post("/sessions/{session_id}/messages")
async def send_message(
    session_id: UUID,
    body: ChatMessageIn,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_role(["patient"]))],
) -> StreamingResponse:
    session = await rag_service.require_patient_session(db, user, session_id)
    await rag_service.persist_user_message(db, session, body.content)
    await db.commit()
    ip_address = client_ip(request)
    query = body.content.strip()

    async def events():
        async with AsyncSessionLocal() as stream_db:
            try:
                stream_session = await rag_service.require_patient_session(
                    stream_db, user, session_id
                )
                async for chunk in rag_service.stream_answer(
                    stream_db,
                    user=user,
                    session=stream_session,
                    query=query,
                    ip_address=ip_address,
                ):
                    yield chunk
            except Exception:
                yield rag_service.sse_pack(
                    "error",
                    {"detail": "The assistant could not generate a reply right now."},
                )
                await stream_db.rollback()

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
