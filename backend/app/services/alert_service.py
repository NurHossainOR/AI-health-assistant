"""Alerts are a mirror of abnormal/critical lab flags — never hand-created, always kept in
sync with a document's flagged fields. No email/push: the frontend polls the count and shows
a dropdown from the bell icon.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import AppError
from app.models.alert import Alert
from app.models.document import Document, DocumentStatus
from app.models.user import User, UserRole
from app.services import trend_service
from app.services.audit_service import write_audit_log
from app.services.consent_service import granted_document_access
from app.services.embedding_service import format_source_date, source_label

logger = logging.getLogger(__name__)

ALERT_SEVERITIES = {"abnormal", "critical"}


@dataclass(frozen=True)
class AlertRow:
    """Pure, DB-free description of one desired alert; makes sync_alerts_for_document testable."""

    metric_key: str
    field_name: str
    value: str
    unit: Optional[str]
    reference_text: Optional[str]
    severity: str
    observed_at: Optional[date]


def _reference_text(low: Optional[float], high: Optional[float]) -> Optional[str]:
    if low is not None and high is not None:
        return f"{low:g}–{high:g}"
    if high is not None:
        return f"< {high:g}"
    if low is not None:
        return f"> {low:g}"
    return None


def compute_alert_rows(points: list[trend_service.LabPoint]) -> list[AlertRow]:
    """The abnormal/critical rows a document's lab points should produce, one per metric.

    A metric already alert-worthy from an earlier field with the same key wins (first seen).
    """
    rows: dict[str, AlertRow] = {}
    for point in points:
        if point.flag not in ALERT_SEVERITIES or point.metric_key in rows:
            continue
        rows[point.metric_key] = AlertRow(
            metric_key=point.metric_key,
            field_name=point.name,
            value=point.raw_value,
            unit=point.unit,
            reference_text=_reference_text(point.reference.low, point.reference.high),
            severity=point.flag,
            observed_at=point.observed,
        )
    return list(rows.values())


async def sync_alerts_for_document(db: AsyncSession, document_id: UUID) -> int:
    """Recompute this document's alerts from its current lab flags. Returns the live count."""
    result = await db.execute(
        select(Document)
        .options(selectinload(Document.extracted_fields))
        .where(Document.id == document_id)
    )
    document = result.scalar_one_or_none()
    if not document or document.status != DocumentStatus.confirmed:
        return 0

    lab_fields = [f for f in document.extracted_fields if f.field_type == "lab"]
    points = [p for p in (trend_service.build_point(f, document) for f in lab_fields) if p]
    desired = {row.metric_key: row for row in compute_alert_rows(points)}

    existing = list(
        (
            await db.execute(select(Alert).where(Alert.document_id == document_id))
        ).scalars()
    )
    existing_by_key = {a.metric_key: a for a in existing}

    for key, alert in existing_by_key.items():
        if key not in desired:
            await db.delete(alert)
    for key, row in desired.items():
        alert = existing_by_key.get(key)
        if alert is None:
            db.add(
                Alert(
                    patient_id=document.patient_id,
                    document_id=document.id,
                    metric_key=row.metric_key,
                    field_name=row.field_name,
                    value=row.value,
                    unit=row.unit,
                    reference_text=row.reference_text,
                    severity=row.severity,
                    observed_at=row.observed_at,
                )
            )
        else:
            alert.field_name = row.field_name
            alert.value = row.value
            alert.unit = row.unit
            alert.reference_text = row.reference_text
            alert.severity = row.severity
            alert.observed_at = row.observed_at
    await db.flush()
    return len(desired)


async def _visible_scope(
    db: AsyncSession, user: User
) -> tuple[Optional[UUID], list[UUID], list[UUID]]:
    """(own_patient_id, fully-granted patient ids, individually-granted document ids)."""
    if user.role == UserRole.patient:
        return user.id, [], []
    if user.role in (UserRole.doctor, UserRole.caregiver):
        full_patient_ids, document_ids = await granted_document_access(db, user)
        return None, full_patient_ids, document_ids
    return None, [], []  # admin: no clinical data access


async def _visible_alerts_query(db: AsyncSession, user: User):
    own_id, full_patient_ids, document_ids = await _visible_scope(db, user)
    if not own_id and not full_patient_ids and not document_ids:
        return None
    stmt = select(Alert)
    if own_id:
        stmt = stmt.where(Alert.patient_id == own_id)
    else:
        from sqlalchemy import or_

        clauses = []
        if full_patient_ids:
            clauses.append(Alert.patient_id.in_(full_patient_ids))
        if document_ids:
            clauses.append(Alert.document_id.in_(document_ids))
        stmt = stmt.where(or_(*clauses))
    return stmt


_SEVERITY_RANK = {"critical": 2, "abnormal": 1}


async def list_alerts(
    db: AsyncSession,
    user: User,
    *,
    unacknowledged_only: bool = False,
    limit: int = 50,
) -> list[Alert]:
    stmt = await _visible_alerts_query(db, user)
    if stmt is None:
        return []
    if unacknowledged_only:
        stmt = stmt.where(Alert.acknowledged_at.is_(None))
    result = await db.execute(stmt.order_by(Alert.created_at.desc()).limit(max(1, min(limit, 200))))
    alerts = list(result.scalars().all())
    alerts.sort(key=lambda a: (-_SEVERITY_RANK.get(a.severity, 0), a.acknowledged_at is not None))
    return alerts


async def unread_count(db: AsyncSession, user: User) -> int:
    stmt = await _visible_alerts_query(db, user)
    if stmt is None:
        return 0
    stmt = stmt.where(Alert.acknowledged_at.is_(None))
    result = await db.execute(stmt)
    return len(result.scalars().all())


async def _labels_for(db: AsyncSession, alerts: list[Alert]) -> dict[UUID, dict[str, str]]:
    if not alerts:
        return {}
    doc_ids = {a.document_id for a in alerts}
    result = await db.execute(select(Document).where(Document.id.in_(doc_ids)))
    labels: dict[UUID, dict[str, str]] = {}
    for doc in result.scalars().all():
        display = (doc.display_name or "").strip() or doc.original_filename
        date_text = format_source_date(doc.confirmed_at or doc.uploaded_at)
        labels[doc.id] = {
            "document_label": source_label(doc.doc_type.value, date_text),
            "document_name": display,
        }
    return labels


async def to_out_rows(db: AsyncSession, alerts: list[Alert]) -> list[dict[str, Any]]:
    labels = await _labels_for(db, alerts)
    rows = []
    for a in alerts:
        meta = labels.get(a.document_id, {})
        rows.append(
            {
                "id": a.id,
                "document_id": a.document_id,
                "patient_id": a.patient_id,
                "metric_key": a.metric_key,
                "field_name": a.field_name,
                "value": a.value,
                "unit": a.unit,
                "reference_text": a.reference_text,
                "severity": a.severity,
                "observed_at": a.observed_at.isoformat() if a.observed_at else None,
                "created_at": a.created_at,
                "acknowledged_at": a.acknowledged_at,
                "document_label": meta.get("document_label"),
                "document_name": meta.get("document_name"),
            }
        )
    return rows


async def _get_visible(db: AsyncSession, user: User, alert_id: UUID) -> Alert:
    stmt = await _visible_alerts_query(db, user)
    alert = await db.get(Alert, alert_id) if stmt is not None else None
    if alert is None:
        raise AppError("Alert not found", status_code=404, code="not_found")
    _, full_patient_ids, document_ids = await _visible_scope(db, user)
    allowed = (
        (user.role == UserRole.patient and alert.patient_id == user.id)
        or alert.patient_id in full_patient_ids
        or alert.document_id in document_ids
    )
    if not allowed:
        raise AppError("Alert not found", status_code=404, code="not_found")
    return alert


async def acknowledge(
    db: AsyncSession, user: User, alert_id: UUID, *, ip_address: Optional[str] = None
) -> Alert:
    alert = await _get_visible(db, user, alert_id)
    if alert.acknowledged_at is None:
        alert.acknowledged_at = datetime.now(timezone.utc)
        alert.acknowledged_by = user.id
        await db.flush()
        await write_audit_log(
            db,
            actor_id=user.id,
            action="alert.acknowledged",
            resource_type="alert",
            resource_id=str(alert.id),
            ip_address=ip_address,
            metadata={"patient_id": str(alert.patient_id), "severity": alert.severity},
        )
    return alert


async def acknowledge_all(
    db: AsyncSession, user: User, *, ip_address: Optional[str] = None
) -> int:
    alerts = await list_alerts(db, user, unacknowledged_only=True, limit=200)
    now = datetime.now(timezone.utc)
    for alert in alerts:
        alert.acknowledged_at = now
        alert.acknowledged_by = user.id
    if alerts:
        await db.flush()
        await write_audit_log(
            db,
            actor_id=user.id,
            action="alert.acknowledged_all",
            resource_type="alert",
            ip_address=ip_address,
            metadata={"count": len(alerts)},
        )
    return len(alerts)
