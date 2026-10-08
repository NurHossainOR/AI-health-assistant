import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class Alert(Base):
    """One abnormal/critical lab flag surfaced to the patient (and consented doctors).

    Kept in sync with a document's lab flags (never hand-edited): one row per
    (document_id, metric_key), created/updated/deleted as flags change on confirm.
    """

    __tablename__ = "alerts"
    __table_args__ = (
        UniqueConstraint("document_id", "metric_key", name="uq_alert_document_metric"),
        Index("ix_alerts_patient_created", "patient_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    metric_key: Mapped[str] = mapped_column(String(64), nullable=False)
    field_name: Mapped[str] = mapped_column(String(255), nullable=False)
    value: Mapped[str] = mapped_column(String(255), nullable=False)
    unit: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    reference_text: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)  # abnormal | critical
    observed_at: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    acknowledged_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
