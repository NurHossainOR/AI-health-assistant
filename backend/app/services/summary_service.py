"""Versioned doctor/patient summaries per confirmed document.

Severity flags are computed by trend_service and injected into the LLM input; any flag the model
returns is overwritten with the stored one, so the LLM only writes prose.
"""

from __future__ import annotations

import asyncio
import copy
import json
import logging
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import AppError
from app.models.document import Document, DocumentStatus
from app.models.summary import (
    DocumentSummary,
    SummaryAudience,
    SummaryStatus,
    SummaryTranslation,
)
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
    summary_input = await build_summary_input(db, document)
    data = json.dumps(summary_input, indent=2, default=str)

    rows: list[DocumentSummary] = []
    for audience, template in PROMPTS.items():
        content: Optional[dict[str, Any]] = None
        model: Optional[str] = None
        error: Optional[str] = None
        if not langchain_llm.llm_configured():
            error = "Summaries are not configured. Set GEMINI_API_KEY or OPENROUTER_API_KEY on the server."
        else:
            content, model = await langchain_llm.generate_json_with_model(
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
            model_version=model,
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
    language: str = "en",
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
                "language": language,
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


# --- Translation ---------------------------------------------------------------------------

SUPPORTED_LANGUAGES = {"en", "bn"}
LANGUAGE_NAMES = {"bn": "Bangla (বাংলা)"}

# Only these prose fields are translated. Names, values, units, references, flags, deltas and
# medications are copied from the English source untouched.
_SCALAR_PROSE = ("overview", "what_this_means")
_LIST_PROSE = ("chief_findings", "items_to_review", "questions_for_doctor")
_NESTED_PROSE = (("findings", "plain_explanation"),)

TRANSLATE_PROMPT = """Translate each value in the JSON object below into natural, simple {language}
for a patient. Keep medical test names, abbreviations (e.g. HbA1c, LDL, MCV), numbers, units and
dates exactly as written. Do not add advice or extra text.
Return JSON only, with exactly the same keys: {{"<key>": "<translated text>", ...}}

{payload}
"""
TRANSLATE_BATCH_SIZE = 12


def _prose_slots(content: dict[str, Any]):
    """Yield (container, key) for each translatable string, in a fixed order."""
    for key in _SCALAR_PROSE:
        if isinstance(content.get(key), str) and content[key].strip():
            yield content, key
    for key in _LIST_PROSE:
        items = content.get(key)
        if isinstance(items, list):
            for i, item in enumerate(items):
                if isinstance(item, str) and item.strip():
                    yield items, i
    for list_key, field_key in _NESTED_PROSE:
        items = content.get(list_key)
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict) and isinstance(item.get(field_key), str) and item[field_key].strip():
                    yield item, field_key


def collect_prose(content: dict[str, Any]) -> list[str]:
    return [container[key] for container, key in _prose_slots(content)]


def apply_prose(content: dict[str, Any], strings: list[str]) -> dict[str, Any]:
    """Deep-copy the English content and swap in translated prose; everything else is unchanged."""
    result = copy.deepcopy(content)
    slots = list(_prose_slots(result))
    if len(slots) != len(strings):
        raise ValueError(f"expected {len(slots)} strings, got {len(strings)}")
    for (container, key), text in zip(slots, strings):
        container[key] = text
    return result


async def _translate_batch(
    batch: list[str], offset: int, language: str
) -> Optional[tuple[list[str], Optional[str]]]:
    keys = [str(offset + i + 1) for i in range(len(batch))]
    reply, model = await langchain_llm.generate_json_with_model(
        TRANSLATE_PROMPT.format(
            language=LANGUAGE_NAMES[language],
            payload=json.dumps(dict(zip(keys, batch)), ensure_ascii=False, indent=1),
        ),
        json_mode=True,
    )
    if not isinstance(reply, dict):
        return None
    values = [reply.get(k) for k in keys]
    if not all(isinstance(v, str) and v.strip() for v in values):
        logger.warning("Translation batch missing %s of %s strings", sum(
            not (isinstance(v, str) and v.strip()) for v in values), len(keys))
        return None
    return values, model


async def _translate_strings(
    strings: list[str], language: str
) -> Optional[tuple[list[str], Optional[str]]]:
    """Translate in numbered batches (run concurrently) so no single reply is long enough to truncate."""
    batches = [
        _translate_batch(strings[offset : offset + TRANSLATE_BATCH_SIZE], offset, language)
        for offset in range(0, len(strings), TRANSLATE_BATCH_SIZE)
    ]
    results = await asyncio.gather(*batches)
    if any(r is None for r in results):
        return None
    translated: list[str] = []
    models: list[str] = []
    for values, model in results:  # type: ignore[misc]
        translated.extend(values)
        if model and model not in models:
            models.append(model)
    return translated, ", ".join(models) or None


async def _existing_translation(
    db: AsyncSession, summary_id: UUID, language: str
) -> Optional[SummaryTranslation]:
    return await db.scalar(
        select(SummaryTranslation).where(
            SummaryTranslation.summary_id == summary_id,
            SummaryTranslation.language == language,
        )
    )


async def translate_summary(
    db: AsyncSession, summary: DocumentSummary, language: str
) -> Optional[dict[str, Any]]:
    """Translated content for a ready summary, created and stored on first request.

    Returns None when translation isn't possible right now; callers fall back to English.
    """
    if language == "en" or language not in SUPPORTED_LANGUAGES:
        return summary.content
    if summary.status != SummaryStatus.ready or not summary.content:
        return None
    existing = await _existing_translation(db, summary.id, language)
    if existing:
        return existing.content

    strings = collect_prose(summary.content)
    if not strings:
        return summary.content
    if not langchain_llm.llm_configured():
        return None
    result = await _translate_strings(strings, language)
    if result is None:
        return None
    translated, model = result
    try:
        content = apply_prose(summary.content, translated)
    except ValueError as exc:
        logger.warning("Summary translation rejected for %s: %s", summary.id, exc)
        return None

    try:
        async with db.begin_nested():
            db.add(
                SummaryTranslation(
                    summary_id=summary.id,
                    patient_id=summary.patient_id,
                    language=language,
                    content=content,
                    model_version=model[:128] if model else None,
                )
            )
    except IntegrityError:
        # Another viewer translated the same version first; use theirs.
        existing = await _existing_translation(db, summary.id, language)
        if existing:
            return existing.content
    return content


# --- Background translation --------------------------------------------------------------
# Free fallback models can take minutes, so translation runs in the worker. Redis keys
# dedupe concurrent requests and briefly remember failures so pollers stop waiting.

TRANSLATION_LOCK_SECONDS = 10 * 60
TRANSLATION_FAILED_SECONDS = 2 * 60


def _lock_key(summary_id: UUID, language: str) -> str:
    return f"sumtr:lock:{summary_id}:{language}"


def _failed_key(summary_id: UUID, language: str) -> str:
    return f"sumtr:failed:{summary_id}:{language}"


def _redis():
    from redis.asyncio import Redis

    from app.core.config import get_settings

    return Redis.from_url(get_settings().redis_url, decode_responses=True)


async def stored_translation(
    db: AsyncSession, summary: DocumentSummary, language: str
) -> Optional[dict[str, Any]]:
    """Translated content if it already exists (or nothing needs translating); never calls the LLM."""
    if not summary.content:
        return None
    if not collect_prose(summary.content):
        return summary.content
    existing = await _existing_translation(db, summary.id, language)
    return existing.content if existing else None


async def request_translation(summary: DocumentSummary, language: str) -> str:
    """Queue a background translation. Returns "pending" or "failed"."""
    client = _redis()
    try:
        if await client.exists(_failed_key(summary.id, language)):
            return "failed"
        acquired = await client.set(
            _lock_key(summary.id, language), "1", nx=True, ex=TRANSLATION_LOCK_SECONDS
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Translation queue unavailable: %s", exc)
        return "failed"
    finally:
        await client.aclose()
    if acquired:
        from app.workers.ingestion import enqueue_translation

        try:
            enqueue_translation(str(summary.id), language)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not enqueue translation for %s: %s", summary.id, exc)
            await _finish_translation(summary.id, language, failed=True)
            return "failed"
    return "pending"


async def _finish_translation(summary_id: UUID, language: str, *, failed: bool) -> None:
    client = _redis()
    try:
        await client.delete(_lock_key(summary_id, language))
        if failed:
            await client.set(_failed_key(summary_id, language), "1", ex=TRANSLATION_FAILED_SECONDS)
    finally:
        await client.aclose()


async def run_translation(db: AsyncSession, summary_id: UUID, language: str) -> bool:
    """Worker entry point: translate and store, then release the lock."""
    content: Optional[dict[str, Any]] = None
    try:
        summary = await db.get(DocumentSummary, summary_id)
        if summary is not None:
            content = await translate_summary(db, summary, language)
    finally:
        await _finish_translation(summary_id, language, failed=content is None)
    return content is not None
