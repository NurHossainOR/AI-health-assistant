from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.document import DocType, DocumentStatus


class UploadUrlRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    display_name: str = Field(min_length=1, max_length=255)
    mime_type: str = Field(min_length=1, max_length=128)
    doc_type_hint: Optional[str] = None
    file_size: int = Field(gt=0, le=25 * 1024 * 1024)
    content_hash: str = Field(min_length=64, max_length=64, pattern=r"^[a-fA-F0-9]{64}$")


class UploadUrlResponse(BaseModel):
    document_id: UUID
    upload_url: str
    method: str = "PUT"
    auth_required: bool = False
    headers: dict[str, str] = Field(default_factory=dict)


class DocumentPatch(BaseModel):
    doc_type: Optional[DocType] = None
    display_name: Optional[str] = Field(default=None, min_length=1, max_length=255)


class ExtractedFieldIn(BaseModel):
    id: Optional[UUID] = None
    field_type: str = "lab"
    name: str
    value: Optional[str] = None
    unit: Optional[str] = None
    reference_low: Optional[str] = None
    reference_high: Optional[str] = None
    observed_at: Optional[str] = None
    source_confidence: Optional[float] = None
    canonical_code: Optional[str] = None


class ExtractedFieldOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    field_type: str
    name: str
    value: Optional[str] = None
    unit: Optional[str] = None
    reference_low: Optional[str] = None
    reference_high: Optional[str] = None
    observed_at: Optional[str] = None
    source_confidence: float
    canonical_code: Optional[str] = None
    flag: Optional[str] = None


class ExtractedFieldsPatch(BaseModel):
    fields: list[ExtractedFieldIn]


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    patient_id: UUID
    uploaded_by: UUID
    doc_type: DocType
    original_filename: str
    display_name: Optional[str] = None
    mime_type: str
    file_size: int
    status: DocumentStatus
    error_message: Optional[str] = None
    uploaded_at: datetime
    confirmed_at: Optional[datetime] = None
    needs_review: bool = False
    retry_count: int = 0


class DocumentStatusOut(DocumentOut):
    stage: str


class ProcessingConsentOut(BaseModel):
    granted: bool
    granted_at: Optional[datetime] = None


class MessageOut(BaseModel):
    message: str
