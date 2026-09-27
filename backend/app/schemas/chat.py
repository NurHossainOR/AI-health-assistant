from datetime import datetime
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.chat import ChatRole


class ChatSessionCreate(BaseModel):
    title: Optional[str] = Field(default=None, max_length=255)


class ChatSessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    patient_id: UUID
    title: str
    created_at: datetime
    updated_at: datetime


class ChatMessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    language: Literal["en", "bn"] = "en"


class CitationOut(BaseModel):
    source_index: int
    document_id: UUID
    doc_type: str
    label: str
    source_date: Optional[str] = None


class ChatMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    session_id: UUID
    role: ChatRole
    content: str
    cited_document_ids: list[UUID] = Field(default_factory=list)
    citations: Optional[list[dict[str, Any]]] = None
    insufficient_context: bool = False
    created_at: datetime
