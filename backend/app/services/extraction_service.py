from __future__ import annotations

import io
import logging
import re
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.models.document import (
    Document,
    DocumentPage,
    DocumentStatus,
    ExtractedField,
    ImagingStudy,
)
from app.services import lab_catalog, langchain_llm, storage_service

logger = logging.getLogger(__name__)

CONFIDENCE_THRESHOLD = 0.75

# Regex fallback patterns; names, codes, units and ranges come from the lab catalog.
_LAB_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("ldl", re.compile(r"LDL[^0-9]{0,24}(\d+(?:\.\d+)?)\s*(mg/?dL|mmol/L)?", re.I)),
    ("hdl", re.compile(r"HDL[^0-9]{0,24}(\d+(?:\.\d+)?)\s*(mg/?dL|mmol/L)?", re.I)),
    ("triglycerides", re.compile(r"Triglycerides?[^0-9]{0,24}(\d+(?:\.\d+)?)\s*(mg/?dL)?", re.I)),
    ("hba1c", re.compile(r"(?:HbA1c|A1C|Hemoglobin A1c)[^0-9]{0,24}(\d+(?:\.\d+)?)\s*%?", re.I)),
    ("glucose", re.compile(r"(?:Glucose|FBS|FBG)[^0-9]{0,24}(\d+(?:\.\d+)?)\s*(mg/?dL)?", re.I)),
]


def _range_str(value: Optional[float]) -> Optional[str]:
    return None if value is None else f"{value:g}"


LAB_SPECS: list[dict[str, Any]] = [
    {
        "name": lab_catalog.BY_KEY[key].name,
        "code": lab_catalog.BY_KEY[key].loinc,
        "pattern": pattern,
        "unit": lab_catalog.BY_KEY[key].unit,
        "low": _range_str(lab_catalog.BY_KEY[key].low),
        "high": _range_str(lab_catalog.BY_KEY[key].high),
    }
    for key, pattern in _LAB_PATTERNS
]

RX_PATTERN = re.compile(
    r"\b([A-Z][a-z]+(?:cillin|mycin|pril|sartan|statin|azole|olol|pine|ide))\s+(\d+\s*mg)\b"
)


async def _load_document(db: AsyncSession, document_id: UUID) -> Document:
    result = await db.execute(
        select(Document)
        .options(
            selectinload(Document.pages),
            selectinload(Document.extracted_fields),
            selectinload(Document.imaging_studies),
        )
        .where(Document.id == document_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise ValueError(f"Document {document_id} not found")
    return doc


async def _read_bytes(doc: Document) -> bytes:
    return await storage_service.aget_object_bytes(doc.storage_key)


def _pdf_text(data: bytes) -> tuple[str, float]:
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        pages = []
        for page in reader.pages:
            pages.append(page.extract_text() or "")
        text = "\n".join(pages).strip()
        return text, 0.9 if len(text) > 40 else 0.4
    except Exception as exc:  # noqa: BLE001
        logger.info("PDF extract failed: %s", exc)
        return "", 0.2


def _prepare_image_bytes(data: bytes) -> tuple[bytes, str]:
    try:
        from PIL import Image

        image = Image.open(io.BytesIO(data))
        image = image.convert("RGB")
        image.thumbnail((2048, 2048))
        buf = io.BytesIO()
        image.save(buf, format="JPEG", quality=85)
        return buf.getvalue(), "image/jpeg"
    except Exception as exc:  # noqa: BLE001
        logger.warning("Image resize skipped: %s", exc)
        return data, "image/jpeg"


def _is_image(doc: Document) -> bool:
    mime = (doc.mime_type or "").lower()
    name = doc.original_filename.lower()
    return mime.startswith("image/") or name.endswith((".png", ".jpg", ".jpeg", ".webp"))


def _placeholder_only(fields: list[ExtractedField]) -> bool:
    if not fields:
        return True
    return all(f.name == "Needs manual review" for f in fields)


def extraction_is_empty(doc: Document) -> bool:
    text = "\n".join((p.ocr_text or "") for p in doc.pages).strip()
    return len(text) < 40 or _placeholder_only(list(doc.extracted_fields))


def _append_regex_fields(doc: Document, text: str) -> int:
    found = 0
    for spec in LAB_SPECS:
        match = spec["pattern"].search(text)
        if not match:
            continue
        found += 1
        unit = match.group(2) if match.lastindex and match.lastindex >= 2 and match.group(2) else spec["unit"]
        doc.extracted_fields.append(
            ExtractedField(
                field_type="lab",
                name=spec["name"],
                value=match.group(1),
                unit=unit.replace("mgdL", "mg/dL") if unit else spec["unit"],
                reference_low=spec["low"],
                reference_high=spec["high"],
                source_confidence=0.88,
                canonical_code=spec["code"],
            )
        )

    for med, dose in RX_PATTERN.findall(text)[:8]:
        found += 1
        doc.extracted_fields.append(
            ExtractedField(
                field_type="medication",
                name=med,
                value=dose,
                unit="mg" if "mg" in dose else None,
                source_confidence=0.7,
                canonical_code=None,
            )
        )

    if doc.imaging_studies:
        study = doc.imaging_studies[0]
        doc.extracted_fields.append(
            ExtractedField(
                field_type="imaging",
                name="Modality",
                value=study.modality or "Unknown",
                source_confidence=0.9,
            )
        )
        if study.body_part:
            doc.extracted_fields.append(
                ExtractedField(
                    field_type="imaging",
                    name="Body part",
                    value=study.body_part,
                    source_confidence=0.85,
                )
            )
        found += 1
    return found


def _apply_llm_fields(doc: Document, payload: dict[str, Any]) -> int:
    fields = payload.get("fields") or []
    count = 0
    for item in fields:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        field_type = str(item.get("field_type") or "other").strip().lower()
        if field_type not in {"lab", "medication", "imaging", "finding", "other"}:
            field_type = "other"
        value = item.get("value")
        doc.extracted_fields.append(
            ExtractedField(
                field_type=field_type,
                name=name[:255],
                value=None if value is None else str(value)[:255],
                unit=None if item.get("unit") is None else str(item.get("unit"))[:64],
                reference_low=None if item.get("reference_low") is None else str(item.get("reference_low"))[:64],
                reference_high=None if item.get("reference_high") is None else str(item.get("reference_high"))[:64],
                observed_at=None if item.get("observed_at") is None else str(item.get("observed_at"))[:32],
                source_confidence=0.86,
                canonical_code=None if item.get("canonical_code") is None else str(item.get("canonical_code"))[:64],
            )
        )
        count += 1
    return count


async def extract_medical_entities(db: AsyncSession, document_id: UUID) -> None:
    doc = await _load_document(db, document_id)
    previous_status = doc.status
    keep_review_status = previous_status in {
        DocumentStatus.confirmed,
        DocumentStatus.needs_review,
        DocumentStatus.extracted,
    } or doc.confirmed_at is not None
    if keep_review_status and previous_status == DocumentStatus.extracting and doc.confirmed_at:
        previous_status = DocumentStatus.confirmed
    if not keep_review_status:
        doc.status = DocumentStatus.extracting
    await db.flush()

    text = "\n".join(p.ocr_text or "" for p in doc.pages)
    file_bytes = b""
    try:
        file_bytes = await _read_bytes(doc)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not load document bytes for extraction: %s", exc)

    mime = doc.mime_type or "application/octet-stream"
    payload = None
    if file_bytes or text.strip():
        send_bytes, send_mime = file_bytes, mime
        if file_bytes and _is_image(doc):
            send_bytes, send_mime = _prepare_image_bytes(file_bytes)
        payload = await langchain_llm.extract_document_json(
            mime_type=send_mime,
            data=send_bytes,
            extra_text=text,
        )

    document_text = ""
    if payload:
        document_text = str(payload.get("document_text") or "").strip()
        if document_text:
            if doc.pages:
                page = doc.pages[0]
                page.ocr_text = document_text
                page.ocr_confidence = max(page.ocr_confidence or 0.0, 0.9)
            else:
                doc.pages.append(
                    DocumentPage(page_number=1, ocr_text=document_text, ocr_confidence=0.9)
                )
            text = document_text

    for field in list(doc.extracted_fields):
        await db.delete(field)
    await db.flush()

    found = 0
    if payload:
        found += _apply_llm_fields(doc, payload)
    if found == 0:
        found += _append_regex_fields(doc, text)

    if found == 0:
        doc.extracted_fields.append(
            ExtractedField(
                field_type="other",
                name="Needs manual review",
                value="No structured values detected automatically",
                source_confidence=0.2,
            )
        )
    if keep_review_status:
        doc.status = previous_status
    await db.flush()


def _dicom_meta(data: bytes) -> dict[str, Any]:
    try:
        import pydicom
        from pydicom.errors import InvalidDicomError

        ds = pydicom.dcmread(io.BytesIO(data), force=True, stop_before_pixels=True)
        def _val(tag: str) -> Optional[str]:
            v = getattr(ds, tag, None)
            return str(v) if v is not None else None

        return {
            "Modality": _val("Modality"),
            "StudyDate": _val("StudyDate"),
            "BodyPartExamined": _val("BodyPartExamined"),
            "StudyDescription": _val("StudyDescription"),
            "PatientAge": _val("PatientAge"),
            "Manufacturer": _val("Manufacturer"),
        }
    except Exception as exc:  # noqa: BLE001
        logger.info("DICOM parse failed: %s", exc)
        return {"error": str(exc)}


async def run_ocr_or_dicom_parse(db: AsyncSession, document_id: UUID) -> None:
    doc = await _load_document(db, document_id)
    doc.status = DocumentStatus.scanning
    await db.flush()

    data = await _read_bytes(doc)
    is_dicom = doc.mime_type == "application/dicom" or doc.original_filename.lower().endswith(".dcm")

    doc.pages.clear()
    await db.flush()

    if is_dicom:
        meta = _dicom_meta(data)
        text = "\n".join(f"{k}: {v}" for k, v in meta.items() if v)
        doc.pages.append(
            DocumentPage(page_number=1, ocr_text=text, ocr_confidence=0.95 if "error" not in meta else 0.3)
        )
        if doc.imaging_studies:
            for row in list(doc.imaging_studies):
                await db.delete(row)
        doc.imaging_studies.append(
            ImagingStudy(
                patient_id=doc.patient_id,
                modality=meta.get("Modality"),
                body_part=meta.get("BodyPartExamined"),
                findings_text=meta.get("StudyDescription"),
                dicom_metadata=meta,
                study_date=meta.get("StudyDate"),
            )
        )
    elif doc.mime_type == "application/pdf" or doc.original_filename.lower().endswith(".pdf"):
        text, conf = _pdf_text(data)
        doc.pages.append(DocumentPage(page_number=1, ocr_text=text, ocr_confidence=conf))
    else:
        # Image OCR is a later worker; store a low-confidence placeholder so review UI appears.
        doc.pages.append(
            DocumentPage(
                page_number=1,
                ocr_text="",
                ocr_confidence=0.25,
            )
        )
    await db.flush()


async def normalize_and_score(db: AsyncSession, document_id: UUID) -> None:
    settings = get_settings()
    threshold = settings.extraction_confidence_threshold or CONFIDENCE_THRESHOLD
    doc = await _load_document(db, document_id)
    doc.status = DocumentStatus.validating
    await db.flush()

    # Terminology already mapped at extract time (LOINC codes on labs).
    confidences = [f.source_confidence for f in doc.extracted_fields] or [0.0]
    lowest = min(confidences)
    if lowest < threshold:
        doc.status = DocumentStatus.needs_review
    else:
        doc.status = DocumentStatus.extracted
    await db.flush()
