import enum
import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class SummaryAudience(str, enum.Enum):
    doctor = "doctor"
    patient = "patient"


class SummaryStatus(str, enum.Enum):
    ready = "ready"
    failed = "failed"


class DocumentSummary(Base):
    """One generated summary version. New versions are appended, never overwritten."""

    __tablename__ = "document_summaries"
    __table_args__ = (
        UniqueConstraint("document_id", "audience", "version_no", name="uq_summary_version"),
        Index("ix_document_summaries_doc_audience", "document_id", "audience"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    audience: Mapped[SummaryAudience] = mapped_column(
        Enum(SummaryAudience, name="summary_audience"), nullable=False
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[SummaryStatus] = mapped_column(
        Enum(SummaryStatus, name="summary_status"), nullable=False, default=SummaryStatus.ready
    )
    content: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    model_version: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
