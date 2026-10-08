from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class AlertOut(BaseModel):
    id: UUID
    document_id: UUID
    patient_id: UUID
    metric_key: str
    field_name: str
    value: str
    unit: Optional[str] = None
    reference_text: Optional[str] = None
    severity: str
    observed_at: Optional[date] = None
    created_at: datetime
    acknowledged_at: Optional[datetime] = None
    document_label: Optional[str] = None
    document_name: Optional[str] = None


class UnreadCountOut(BaseModel):
    count: int


class AcknowledgeAllOut(BaseModel):
    acknowledged: int
