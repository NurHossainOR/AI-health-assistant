from __future__ import annotations

import io
import logging
import re
from datetime import datetime, timezone
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
from app.services import storage_service

logger = logging.getLogger(__name__)

CONFIDENCE_THRESHOLD = 0.75

LAB_SPECS: list[dict[str, Any]] = [
    {
        "name": "LDL Cholesterol",
        "code": "13457-7",
        "pattern": re.compile(r"LDL[^0-9]{0,24}(\d+(?:\.\d+)?)\s*(mg/?dL|mmol/L)?", re.I),
        "unit": "mg/dL",
        "low": None,
        "high": "130",
    },
    {
        "name": "HDL Cholesterol",
        "code": "2085-9",
        "pattern": re.compile(r"HDL[^0-9]{0,24}(\d+(?:\.\d+)?)\s*(mg/?dL|mmol/L)?", re.I),
        "unit": "mg/dL",
        "low": "40",
        "high": None,
    },
    {
        "name": "Triglycerides",
        "code": "2571-8",
        "pattern": re.compile(r"Triglycerides?[^0-9]{0,24}(\d+(?:\.\d+)?)\s*(mg/?dL)?", re.I),
        "unit": "mg/dL",
        "low": None,
        "high": "150",
    },
    {
        "name": "Hemoglobin A1c",
        "code": "4548-4",
        "pattern": re.compile(r"(?:HbA1c|A1C|Hemoglobin A1c)[^0-9]{0,24}(\d+(?:\.\d+)?)\s*%?", re.I),
        "unit": "%",
        "low": "4.0",
        "high": "5.6",
    },
    {
        "name": "Glucose",
        "code": "2345-7",
        "pattern": re.compile(r"(?:Glucose|FBS|FBG)[^0-9]{0,24}(\d+(?:\.\d+)?)\s*(mg/?dL)?", re.I),
        "unit": "mg/dL",
        "low": "70",
        "high": "99",
    },
]

RX_PATTERN = re.compile(
    r"\b([A-Z][a-z]+(?:cillin|mycin|pril|sartan|statin|azole|olol|pine|ide))\s+(\d+\s*mg)\b"
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


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


def _read_bytes(doc: Document) -> bytes:
    return storage_service.get_object_bytes(doc.storage_key)


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

    data = _read_bytes(doc)
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


async def extract_medical_entities(db: AsyncSession, document_id: UUID) -> None:
    doc = await _load_document(db, document_id)
    doc.status = DocumentStatus.extracting
    await db.flush()

    text = "\n".join(p.ocr_text or "" for p in doc.pages)
    for field in list(doc.extracted_fields):
        await db.delete(field)
    await db.flush()

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

    if found == 0:
        doc.extracted_fields.append(
            ExtractedField(
                field_type="other",
                name="Needs manual review",
                value="No structured values detected automatically",
                source_confidence=0.2,
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
        doc.confirmed_at = _utcnow()
        doc.status = DocumentStatus.confirmed
    await db.flush()
