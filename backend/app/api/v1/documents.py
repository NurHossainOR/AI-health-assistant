from typing import Annotated
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import client_ip, get_current_user, require_role
from app.db.session import get_db
from app.models.user import User
from app.schemas.documents import (
    DocumentOut,
    DocumentPatch,
    DocumentStatusOut,
    ExtractedFieldOut,
    ExtractedFieldsPatch,
    UploadUrlRequest,
    UploadUrlResponse,
)
from app.services import document_service

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/upload-url", response_model=UploadUrlResponse)
async def upload_url(
    body: UploadUrlRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_role(["patient"]))],
) -> UploadUrlResponse:
    return await document_service.create_upload_url(
        db, user, body, ip_address=client_ip(request)
    )


@router.put("/{document_id}/content")
async def upload_content(
    document_id: UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_role(["patient"]))],
) -> dict[str, str]:
    body = await request.body()
    await document_service.store_uploaded_bytes(db, user, document_id, body)
    return {"status": "uploaded"}


@router.post("/{document_id}/complete", response_model=DocumentStatusOut)
async def complete_upload(
    document_id: UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_role(["patient"]))],
) -> DocumentStatusOut:
    return await document_service.complete_upload(
        db, user, document_id, ip_address=client_ip(request)
    )


@router.get("", response_model=list[DocumentOut])
async def list_documents(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> list[DocumentOut]:
    return await document_service.list_documents(db, user)


@router.get("/{document_id}/status", response_model=DocumentStatusOut)
async def document_status(
    document_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> DocumentStatusOut:
    return await document_service.get_status(db, user, document_id)


@router.patch("/{document_id}", response_model=DocumentOut)
async def patch_document(
    document_id: UUID,
    body: DocumentPatch,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_role(["patient"]))],
) -> DocumentOut:
    if body.doc_type is None and body.display_name is None:
        from app.core.exceptions import AppError

        raise AppError("Nothing to update", status_code=400)
    return await document_service.patch_document(db, user, document_id, body)


@router.get("/{document_id}/extracted-fields", response_model=list[ExtractedFieldOut])
async def get_extracted_fields(
    document_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> list[ExtractedFieldOut]:
    return await document_service.get_extracted_fields(db, user, document_id)


@router.patch("/{document_id}/extracted-fields", response_model=list[ExtractedFieldOut])
async def patch_extracted_fields(
    document_id: UUID,
    body: ExtractedFieldsPatch,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_role(["patient"]))],
) -> list[ExtractedFieldOut]:
    return await document_service.save_extracted_fields(db, user, document_id, body.fields)


@router.post("/{document_id}/confirm", response_model=DocumentStatusOut)
async def confirm_document(
    document_id: UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_role(["patient"]))],
) -> DocumentStatusOut:
    return await document_service.confirm_document(
        db, user, document_id, ip_address=client_ip(request)
    )


@router.post("/{document_id}/retry", response_model=DocumentStatusOut)
async def retry_document(
    document_id: UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_role(["patient"]))],
) -> DocumentStatusOut:
    return await document_service.retry_document(
        db, user, document_id, ip_address=client_ip(request)
    )


@router.get("/{document_id}/file")
async def download_file(
    document_id: UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> Response:
    data, mime_type, filename = await document_service.get_file(
        db, user, document_id, ip_address=client_ip(request)
    )
    safe_name = (filename or "document").replace('"', "")
    return Response(
        content=data,
        media_type=mime_type or "application/octet-stream",
        headers={
            "Content-Disposition": (
                f'inline; filename="{safe_name}"; '
                f"filename*=UTF-8''{quote(safe_name)}"
            ),
        },
    )
