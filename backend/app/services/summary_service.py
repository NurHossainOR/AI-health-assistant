"""Versioned doctor/patient summaries per confirmed document.

Severity flags are computed by trend_service and injected into the LLM input; any flag the model
returns is overwritten with the stored one, so the LLM only writes prose.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.models.document import Document, DocumentStatus
from app.models.summary import DocumentSummary, SummaryAudience, SummaryStatus
from app.models.user import User, UserRole
from app.services import lab_catalog, langchain_llm, trend_service
from app.services.audit_service import write_audit_log
from app.services.embedding_service import document_type_label, format_source_date

logger = logging.getLogger(__name__)

GUARDRAILS = """STRICT RULES:
- Use only the data provided below. Never invent values, dates, tests or documents.
- Never suggest a diagnosis, never recommend starting, stopping or changing a treatment or medication,
  and never speculate about causes of abnormal values.
- Severity flags are already computed. Repeat them exactly; do not re-grade any value.
- If data is missing, ambiguous or conflicting, say so plainly.
"""

DOCTOR_PROMPT = """You write a concise clinical summary of one patient report for a physician.
Terse, clinical terminology, bullet-first, no filler.
{guardrails}
Return JSON only with this shape:
{{
  "chief_findings": ["short clinical bullet", ...],
  "abnormal_values": [{{"name": str, "value": str, "unit": str|null, "reference": str|null,
                        "flag": str, "previous": str|null, "delta": str|null}}],
  "medications": ["name dose frequency", ...],
  "items_to_review": ["data point worth clinician attention, phrased as an observation", ...]
}}
Include in abnormal_values only labs whose flag is borderline, abnormal or critical.

Report data:
{data}
"""

PATIENT_PROMPT = """You explain one medical report to the patient in plain, warm, simple language
(about a 6th-grade reading level). Explain what each test measures in general terms.
{guardrails}
Return JSON only with this shape:
{{
  "overview": "2-3 sentence plain summary of the report",
  "findings": [{{"name": str, "value": str, "unit": str|null, "flag": str,
                 "plain_explanation": "what this test measures and where this value sits vs the range"}}],
  "what_this_means": "short paragraph; informational only, no diagnosis",
  "questions_for_doctor": ["question the patient could ask their doctor", ...]
}}

Report data:
{data}
"""

PROMPTS = {SummaryAudience.doctor: DOCTOR_PROMPT, SummaryAudience.patient: PATIENT_PROMPT}


def _fmt(value: Optional[float]) -> Optional[str]:
    return None if value is None else f"{value:g}"


def _reference_text(low: Optional[float], high: Optional[float]) -> Optional[str]:
    if low is not None and high is not None:
        return f"{low:g}-{high:g}"
    if high is not None:
        return f"<{high:g}"
    if low is not None:
        return f">{low:g}"
    return None


async def _load(db: AsyncSession, document_id: UUID) -> Optional[Document]:
    result = await db.execute(
        select(Document)
        .options(selectinload(Document.extracted_fields), selectinload(Document.imaging_studies))
        .where(Document.id == document_id)
    )
    return result.scalar_one_or_none()


async def build_summary_input(db: AsyncSession, document: Document) -> dict[str, Any]:
    history = await trend_service.lab_points_for_patient(db, document.patient_id)
    previous = {p.metric_key: p for p in trend_service.latest_before(history, document.id)}

    labs: list[dict[str, Any]] = []
    medications: list[dict[str, Any]] = []
    other: list[dict[str, Any]] = []
    for field_row in document.extracted_fields:
        if field_row.name == "Needs manual review":
            continue
        if field_row.field_type == "lab":
            point = trend_service.build_point(field_row, document)
            flag = field_row.flag or trend_service.flag_field(field_row)
            entry: dict[str, Any] = {
                "name": point.name if point else field_row.name,
                "value": field_row.value,
                "unit": field_row.unit,
                "reference": _reference_text(point.reference.low, point.reference.high)
                if point
                else None,
                "flag": flag,
            }
            prev = previous.get(point.metric_key) if point else None
            if prev and point:
                entry["previous"] = f"{prev.raw_value} on {prev.observed.isoformat()}"
                entry["delta"] = _fmt(round(point.value - prev.value, 4))
            labs.append(entry)
        elif field_row.field_type == "medication":
            medications.append({"name": field_row.name, "dose": field_row.value, "unit": field_row.unit})
        else:
            other.append({"name": field_row.name, "value": field_row.value})

    imaging = [
        {
            "modality": s.modality,
            "body_part": s.body_part,
            "study_date": s.study_date,
            "findings": s.findings_text,
        }
        for s in document.imaging_studies
    ]
    return {
        "document_type": document_type_label(document.doc_type.value),
        "report_date": format_source_date(document.confirmed_at or document.uploaded_at),
        "labs": labs,
        "medications": medications,
        "imaging": imaging,
        "other_fields": other,
    }


def enforce_flags(content: dict[str, Any], labs: list[dict[str, Any]]) -> dict[str, Any]:
    """Overwrite any flag the LLM produced with the deterministic one, matched by canonical metric."""
    stored = {lab_catalog.canonical_key(str(lab["name"])): lab["flag"] for lab in labs}
    for key in ("abnormal_values", "findings"):
        items = content.get(key)
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            key = lab_catalog.canonical_key(str(item.get("name") or ""))
            item["flag"] = stored.get(key, "unknown")
    return content


async def _next_version(db: AsyncSession, document_id: UUID, audience: SummaryAudience) -> int:
    current = await db.scalar(
        select(func.max(DocumentSummary.version_no)).where(
            DocumentSummary.document_id == document_id,
            DocumentSummary.audience == audience,
        )
    )
    return int(current or 0) + 1


async def generate_summaries(db: AsyncSession, document_id: UUID) -> list[DocumentSummary]:
    document = await _load(db, document_id)
    if not document or document.status != DocumentStatus.confirmed:
        return []
    settings = get_settings()
    summary_input = await build_summary_input(db, document)
    data = json.dumps(summary_input, indent=2, default=str)

    rows: list[DocumentSummary] = []
    for audience, template in PROMPTS.items():
        content: Optional[dict[str, Any]] = None
        error: Optional[str] = None
        if not settings.gemini_api_key:
            error = "Summaries are not configured. Set GEMINI_API_KEY on the server."
        else:
            content = await langchain_llm.generate_json(
                template.format(guardrails=GUARDRAILS, data=data)
            )
            if content is None:
                error = "The summary could not be generated. Try regenerating."
        row = DocumentSummary(
            document_id=document.id,
            patient_id=document.patient_id,
            audience=audience,
            version_no=await _next_version(db, document.id, audience),
            status=SummaryStatus.ready if content is not None else SummaryStatus.failed,
            content=enforce_flags(content, summary_input["labs"]) if content is not None else None,
            model_version=settings.gemini_chat_model,
            error_message=error,
        )
        db.add(row)
        await db.flush()
        rows.append(row)
    return rows


async def _get_accessible_document(db: AsyncSession, user: User, document_id: UUID) -> Document:
    from app.services.document_service import _get_accessible

    return await _get_accessible(db, user, document_id)


async def get_summary(
    db: AsyncSession,
    user: User,
    document_id: UUID,
    audience: SummaryAudience,
    *,
    version: Optional[int] = None,
    ip_address: Optional[str] = None,
) -> Optional[DocumentSummary]:
    document = await _get_accessible_document(db, user, document_id)
    q = select(DocumentSummary).where(
        DocumentSummary.document_id == document.id,
        DocumentSummary.audience == audience,
    )
    if version is not None:
        q = q.where(DocumentSummary.version_no == version)
    summary = await db.scalar(q.order_by(DocumentSummary.version_no.desc()).limit(1))
    if version is not None and summary is None:
        raise AppError("Summary version not found", status_code=404, code="not_found")
    if summary and user.id != document.patient_id:
        await write_audit_log(
            db,
            actor_id=user.id,
            action="summary.viewed",
            resource_type="document_summary",
            resource_id=str(summary.id),
            ip_address=ip_address,
            metadata={
                "patient_id": str(document.patient_id),
                "document_id": str(document.id),
                "audience": audience.value,
                "version_no": summary.version_no,
            },
        )
    return summary


async def list_versions(
    db: AsyncSession, user: User, document_id: UUID
) -> list[DocumentSummary]:
    document = await _get_accessible_document(db, user, document_id)
    result = await db.execute(
        select(DocumentSummary)
        .where(DocumentSummary.document_id == document.id)
        .order_by(DocumentSummary.audience, DocumentSummary.version_no.desc())
    )
    return list(result.scalars().all())


async def request_regeneration(db: AsyncSession, user: User, document_id: UUID) -> Document:
    from app.services.document_service import _get_owned

    if user.role != UserRole.patient:
        raise AppError("Only the patient can regenerate summaries", status_code=403)
    document = await _get_owned(db, user, document_id)
    if document.status != DocumentStatus.confirmed:
        raise AppError("Confirm the document before generating summaries", status_code=400)
    return document
