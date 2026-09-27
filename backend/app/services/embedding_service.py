from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.document import Document, DocumentStatus, ExtractedField, ImagingStudy
from app.services import vectorstore

logger = logging.getLogger(__name__)

DOC_TYPE_LABELS = {
    "blood_test": "Blood test",
    "prescription": "Prescription",
    "mri": "MRI",
    "ct": "CT",
    "discharge": "Discharge summary",
    "other": "Document",
}


def document_type_label(doc_type: str) -> str:
    return DOC_TYPE_LABELS.get(doc_type, doc_type.replace("_", " ").title())


def format_source_date(value: Optional[datetime]) -> str:
    if not value:
        return ""
    return value.strftime("%B %d, %Y").replace(" 0", " ")


def source_label(doc_type: str, source_date: str) -> str:
    name = document_type_label(doc_type)
    return f"{name}, {source_date}" if source_date else name


def _field_line(field: ExtractedField) -> str:
    line = field.name
    if field.value:
        line += f": {field.value}"
        if field.unit:
            line += f" {field.unit}"
    elif field.unit:
        line += f" ({field.unit})"
    if field.reference_low or field.reference_high:
        line += f" (reference {field.reference_low or '—'}–{field.reference_high or '—'})"
    if field.observed_at:
        line += f"; observed {field.observed_at}"
    return line


def build_normalized_chunks(
    document: Document,
    fields: list[ExtractedField],
    studies: list[ImagingStudy],
) -> list[dict[str, Any]]:
    """Chunk confirmed structured data only — never the raw OCR dump."""
    doc_type = document.doc_type.value if hasattr(document.doc_type, "value") else str(document.doc_type)
    source_date = format_source_date(document.confirmed_at or document.uploaded_at)
    label = source_label(doc_type, source_date)
    display = (document.display_name or "").strip() or document.original_filename
    base_meta = {
        "document_id": str(document.id),
        "patient_id": str(document.patient_id),
        "doc_type": doc_type,
        "source_date": source_date,
        "label": label,
        "display_name": display,
    }
    chunks: list[dict[str, Any]] = []

    labs = [f for f in fields if f.field_type == "lab"]
    meds = [f for f in fields if f.field_type == "medication"]
    other = [
        f
        for f in fields
        if f.field_type not in {"lab", "medication", "imaging"}
        and f.name != "Needs manual review"
    ]

    if labs:
        body = "\n".join(_field_line(f) for f in labs)
        chunks.append(
            {
                "chunk_text": f"{label}. Structured lab values from '{display}':\n{body}",
                "metadata": {**base_meta, "chunk_kind": "labs"},
            }
        )
    if meds:
        body = "\n".join(_field_line(f) for f in meds)
        chunks.append(
            {
                "chunk_text": f"{label}. Medications from '{display}':\n{body}",
                "metadata": {**base_meta, "chunk_kind": "medications"},
            }
        )
    if other:
        body = "\n".join(_field_line(f) for f in other)
        chunks.append(
            {
                "chunk_text": f"{label}. Other extracted fields from '{display}':\n{body}",
                "metadata": {**base_meta, "chunk_kind": "other_fields"},
            }
        )
    for study in studies:
        bits = [f"{label}. Imaging study from '{display}'."]
        if study.modality:
            bits.append(f"Modality: {study.modality}.")
        if study.body_part:
            bits.append(f"Body part: {study.body_part}.")
        if study.study_date:
            bits.append(f"Study date: {study.study_date}.")
        if study.findings_text:
            bits.append(f"Findings: {study.findings_text}.")
        chunks.append(
            {
                "chunk_text": " ".join(bits),
                "metadata": {**base_meta, "chunk_kind": "imaging"},
            }
        )
    narrative = "\n".join((p.ocr_text or "").strip() for p in getattr(document, "pages", []) or []).strip()
    if narrative and "No structured values detected automatically" not in narrative:
        for i, piece in enumerate(_split_text(narrative)):
            chunks.append(
                {
                    "chunk_text": f"{label}. Report text from '{display}':\n{piece}",
                    "metadata": {**base_meta, "chunk_kind": f"text_{i}"},
                }
            )
    return chunks


def _split_text(text: str, size: int = 900, overlap: int = 80) -> list[str]:
    cleaned = " ".join(text.split())
    if len(cleaned) <= size:
        return [cleaned]
    pieces: list[str] = []
    start = 0
    while start < len(cleaned):
        end = min(len(cleaned), start + size)
        pieces.append(cleaned[start:end])
        if end >= len(cleaned):
            break
        start = max(end - overlap, start + 1)
    return pieces[:8]


async def index_document(db: AsyncSession, document_id: UUID) -> int:
    result = await db.execute(
        select(Document)
        .options(
            selectinload(Document.extracted_fields),
            selectinload(Document.imaging_studies),
            selectinload(Document.pages),
        )
        .where(Document.id == document_id)
    )
    document = result.scalar_one_or_none()
    if not document or document.status != DocumentStatus.confirmed:
        return 0

    passages = build_normalized_chunks(
        document, list(document.extracted_fields), list(document.imaging_studies)
    )
    try:
        await vectorstore.adelete_document_chunks(document.id)
        if not passages:
            document.indexed_at = datetime.now(timezone.utc)
            await db.flush()
            return 0
        count = await vectorstore.aadd_chunks(passages)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Skipping Chroma index for %s: %s", document_id, exc)
        return 0
    document.indexed_at = datetime.now(timezone.utc)
    await db.flush()
    logger.info("Indexed %s Chroma chunks for document %s", count, document_id)
    return count


async def ensure_patient_indexed(db: AsyncSession, patient_id: UUID) -> None:
    """Index confirmed documents missing indexed_at. Never re-extract."""
    pending = await db.execute(
        select(Document.id).where(
            Document.patient_id == patient_id,
            Document.status == DocumentStatus.confirmed,
            Document.indexed_at.is_(None),
        )
    )
    for document_id in pending.scalars().all():
        try:
            await index_document(db, document_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Chroma backfill skipped for %s: %s", document_id, exc)
