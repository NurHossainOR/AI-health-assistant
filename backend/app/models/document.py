import enum
import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class DocType(str, enum.Enum):
    blood_test = "blood_test"
    prescription = "prescription"
    mri = "mri"
    ct = "ct"
    discharge = "discharge"
    other = "other"


class DocumentStatus(str, enum.Enum):
    awaiting_upload = "awaiting_upload"
    uploaded = "uploaded"
    pending = "pending"
    scanning = "scanning"
    extracting = "extracting"
    validating = "validating"
    needs_review = "needs_review"
    extracted = "extracted"
    confirmed = "confirmed"
    failed = "failed"
    retrying = "retrying"


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        Index("ix_documents_patient_uploaded", "patient_id", "uploaded_at"),
        Index("ix_documents_patient_hash", "patient_id", "file_hash"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    doc_type: Mapped[DocType] = mapped_column(
        Enum(DocType, name="doc_type"), nullable=False, default=DocType.other
    )
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    file_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus, name="document_status"),
        nullable=False,
        default=DocumentStatus.awaiting_upload,
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    indexed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    pages: Mapped[list["DocumentPage"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    extracted_fields: Mapped[list["ExtractedField"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    imaging_studies: Mapped[list["ImagingStudy"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class DocumentPage(Base):
    __tablename__ = "document_pages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    ocr_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ocr_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    document: Mapped["Document"] = relationship(back_populates="pages")


class ExtractedField(Base):
    """Draft extraction row — confirmed only after patient review or high confidence."""

    __tablename__ = "extracted_fields"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    field_type: Mapped[str] = mapped_column(String(32), nullable=False, default="lab")
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    value: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    unit: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    reference_low: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    reference_high: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    observed_at: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    source_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    canonical_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    # normal | borderline | abnormal | critical | unknown — set by trend_service on confirm
    flag: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)

    document: Mapped["Document"] = relationship(back_populates="extracted_fields")


class ImagingStudy(Base):
    __tablename__ = "imaging_studies"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    modality: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    body_part: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    findings_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    dicom_metadata: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    study_date: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    document: Mapped["Document"] = relationship(back_populates="imaging_studies")
