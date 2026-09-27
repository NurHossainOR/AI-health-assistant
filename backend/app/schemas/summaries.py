from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.summary import SummaryAudience


class SummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    status: str  # ready | failed | pending
    document_id: UUID
    audience: SummaryAudience
    id: Optional[UUID] = None
    version_no: Optional[int] = None
    content: Optional[dict[str, Any]] = None
    model_version: Optional[str] = None
    error_message: Optional[str] = None
    generated_at: Optional[datetime] = None


class SummaryVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    audience: SummaryAudience
    version_no: int
    status: str
    model_version: Optional[str] = None
    generated_at: datetime
