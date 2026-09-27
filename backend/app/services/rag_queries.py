from __future__ import annotations

from typing import Sequence
from uuid import UUID

from sqlalchemy import Select, or_, select

from app.models.document import Document, DocumentStatus, ExtractedField, ImagingStudy

# Application-level tenant filter — never omit.


def _ilike_contains(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def patient_scoped_structured_query(
    patient_id: UUID,
    *,
    names: Sequence[str],
    entity_type: str = "any",
    limit: int = 20,
) -> Select:
    stmt = (
        select(ExtractedField, Document)
        .join(Document, ExtractedField.document_id == Document.id)
        .where(
            Document.patient_id == patient_id,
            Document.status == DocumentStatus.confirmed,
        )
    )
    if entity_type in {"lab", "medication", "imaging"}:
        stmt = stmt.where(ExtractedField.field_type == entity_type)
    cleaned = [n.strip() for n in names if n and n.strip()]
    if cleaned:
        stmt = stmt.where(
            or_(
                *[
                    ExtractedField.name.ilike(_ilike_contains(name), escape="\\")
                    for name in cleaned
                ]
            )
        )
    return stmt.order_by(
        ExtractedField.observed_at.desc().nulls_last(),
        Document.uploaded_at.desc(),
    ).limit(limit)


def patient_scoped_imaging_query(patient_id: UUID, *, limit: int = 12) -> Select:
    return (
        select(ImagingStudy, Document)
        .join(Document, ImagingStudy.document_id == Document.id)
        .where(
            Document.patient_id == patient_id,
            Document.status == DocumentStatus.confirmed,
        )
        .order_by(Document.uploaded_at.desc())
        .limit(limit)
    )


def patient_scoped_lab_query(
    patient_id: UUID,
    *,
    document_ids: Sequence[UUID] | None = None,
) -> Select:
    """Every confirmed lab field for one patient, optionally narrowed to specific documents."""
    stmt = (
        select(ExtractedField, Document)
        .join(Document, ExtractedField.document_id == Document.id)
        .where(
            Document.patient_id == patient_id,
            Document.status == DocumentStatus.confirmed,
            ExtractedField.field_type == "lab",
        )
    )
    if document_ids is not None:
        stmt = stmt.where(Document.id.in_(list(document_ids)))
    return stmt.order_by(Document.uploaded_at.asc())
