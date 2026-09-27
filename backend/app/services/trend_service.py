"""Deterministic lab flags and trends. Severity is always computed here, never by the LLM."""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Optional, Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.document import ExtractedField
from app.models.user import User, UserRole
from app.services import lab_catalog
from app.services.audit_service import write_audit_log
from app.services.consent_service import granted_document_access
from app.services.rag_queries import patient_scoped_lab_query

FLAGS = ("normal", "borderline", "abnormal", "critical", "unknown")
FLAG_RANK = {"unknown": 0, "normal": 1, "borderline": 2, "abnormal": 3, "critical": 4}

BORDERLINE_RATIO = 0.10
CRITICAL_RATIO = 0.50
ZSCORE_MIN_PRIORS = 3
ZSCORE_SIGNIFICANT = 2.0

_NUMBER_RE = re.compile(r"[-+]?\d*\.?\d+")
_RANGE_RE = re.compile(r"^\s*([-+]?\d*\.?\d+)\s*(?:-|–|—|to)\s*([-+]?\d*\.?\d+)")
_DATE_FORMATS = (
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%d.%m.%Y",
    "%d %b %Y",
    "%d %B %Y",
    "%b %d, %Y",
    "%B %d, %Y",
    "%d-%b-%Y",
    "%Y/%m/%d",
)


def parse_numeric(raw: Optional[str]) -> Optional[float]:
    """First number in a value like "5.6 %", "<130", "1,250"; None for "Negative" etc."""
    if raw is None:
        return None
    match = _NUMBER_RE.search(str(raw).replace(",", ""))
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _parse_bound(raw: Optional[str]) -> tuple[Optional[float], Optional[float]]:
    """One reference string → (low, high). Handles "70-99", "<130", ">40" and plain numbers."""
    if raw is None or not str(raw).strip():
        return None, None
    text = str(raw).strip().replace(",", "")
    match = _RANGE_RE.match(text)
    if match:
        return float(match.group(1)), float(match.group(2))
    if text[0] in "<≤":
        return None, parse_numeric(text)
    if text[0] in ">≥":
        return parse_numeric(text), None
    return parse_numeric(text), None


def parse_range(
    low: Optional[str], high: Optional[str]
) -> tuple[Optional[float], Optional[float]]:
    low_a, high_a = _parse_bound(low)
    low_b, high_b = _parse_bound(high)
    # A plain number in the "high" column is the upper bound, not a lower one.
    if high is not None and str(high).strip() and high_b is None and low_b is not None:
        if not str(high).strip().startswith((">", "≥")):
            high_b, low_b = low_b, None
    resolved_low = low_a if low_a is not None else low_b
    resolved_high = high_b if high_b is not None else high_a
    return resolved_low, resolved_high


def flag_value(
    value: Optional[float],
    low: Optional[float],
    high: Optional[float],
    critical_low: Optional[float] = None,
    critical_high: Optional[float] = None,
) -> str:
    if value is None:
        return "unknown"
    if critical_high is not None and value >= critical_high:
        return "critical"
    if critical_low is not None and value <= critical_low:
        return "critical"
    if low is None and high is None:
        return "unknown"
    if high is not None and value > high:
        deviation, bound = value - high, high
    elif low is not None and value < low:
        deviation, bound = low - value, low
    else:
        return "normal"
    # Deviation relative to the crossed bound (or the range width, if wider), so narrow ranges
    # like glucose 70-99 don't turn every mild excursion into "critical".
    width = (high - low) if (low is not None and high is not None and high > low) else 0.0
    scale = max(width, abs(bound))
    ratio = deviation / scale if scale else float("inf")
    # Metrics with explicit critical thresholds are only critical at those thresholds.
    if critical_low is None and critical_high is None and ratio > CRITICAL_RATIO:
        return "critical"
    if ratio > BORDERLINE_RATIO:
        return "abnormal"
    return "borderline"


def parse_date(raw: Optional[str]) -> Optional[date]:
    if not raw or not str(raw).strip():
        return None
    text = str(raw).strip()
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        pass
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def observed_date(field_row: Any, document: Any) -> date:
    parsed = parse_date(getattr(field_row, "observed_at", None))
    if parsed:
        return parsed
    fallback = getattr(document, "confirmed_at", None) or getattr(document, "uploaded_at", None)
    return fallback.date() if fallback else date.today()


@dataclass
class Reference:
    low: Optional[float]
    high: Optional[float]
    critical_low: Optional[float] = None
    critical_high: Optional[float] = None
    source: str = "report"  # report | catalog | none


def resolve_reference(field_row: Any, metric: Optional[lab_catalog.LabMetric]) -> Reference:
    low, high = parse_range(field_row.reference_low, field_row.reference_high)
    compatible = metric is not None and lab_catalog.unit_compatible(metric, field_row.unit)
    crit_low = metric.critical_low if compatible else None
    crit_high = metric.critical_high if compatible else None
    if low is not None or high is not None:
        return Reference(low, high, crit_low, crit_high, "report")
    if compatible and (metric.low is not None or metric.high is not None):
        return Reference(metric.low, metric.high, crit_low, crit_high, "catalog")
    return Reference(None, None, crit_low, crit_high, "none")


def flag_field(field_row: Any) -> str:
    metric = lab_catalog.lookup(field_row.name, field_row.canonical_code)
    ref = resolve_reference(field_row, metric)
    return flag_value(
        parse_numeric(field_row.value), ref.low, ref.high, ref.critical_low, ref.critical_high
    )


@dataclass
class LabPoint:
    metric_key: str
    name: str
    value: float
    raw_value: str
    unit: Optional[str]
    reference: Reference
    flag: str
    observed: date
    document_id: UUID
    document_name: str
    extras: dict[str, Any] = field(default_factory=dict)


def build_point(field_row: Any, document: Any) -> Optional[LabPoint]:
    value = parse_numeric(field_row.value)
    if value is None:
        return None
    metric = lab_catalog.lookup(field_row.name, field_row.canonical_code)
    ref = resolve_reference(field_row, metric)
    flag = field_row.flag or flag_value(value, ref.low, ref.high, ref.critical_low, ref.critical_high)
    return LabPoint(
        metric_key=metric.key if metric else lab_catalog.slug(field_row.name),
        name=metric.name if metric else field_row.name,
        value=value,
        raw_value=str(field_row.value),
        unit=field_row.unit or (metric.unit if metric else None),
        reference=ref,
        flag=flag,
        observed=observed_date(field_row, document),
        document_id=document.id,
        document_name=(getattr(document, "display_name", None) or "").strip()
        or document.original_filename,
    )


def compute_series(points: Sequence[LabPoint]) -> list[dict[str, Any]]:
    """Sort by date and attach delta / % change vs the previous point and a z-score vs prior baseline."""
    ordered = sorted(points, key=lambda p: p.observed)
    series: list[dict[str, Any]] = []
    for i, point in enumerate(ordered):
        prev = ordered[i - 1] if i > 0 else None
        delta = point.value - prev.value if prev else None
        pct = (delta / prev.value * 100) if prev and prev.value else None
        direction = None
        if delta is not None:
            direction = "up" if delta > 0 else "down" if delta < 0 else "flat"
        zscore = None
        priors = [p.value for p in ordered[:i]]
        if len(priors) >= ZSCORE_MIN_PRIORS:
            stdev = statistics.stdev(priors)
            if stdev > 0:
                zscore = (point.value - statistics.mean(priors)) / stdev
        series.append(
            {
                "date": point.observed.isoformat(),
                "value": point.value,
                "raw_value": point.raw_value,
                "unit": point.unit,
                "flag": point.flag,
                "reference_low": point.reference.low,
                "reference_high": point.reference.high,
                "document_id": str(point.document_id),
                "document_name": point.document_name,
                "previous": prev.value if prev else None,
                "delta": round(delta, 4) if delta is not None else None,
                "pct_change": round(pct, 2) if pct is not None else None,
                "direction": direction,
                "zscore": round(zscore, 2) if zscore is not None else None,
                "significant_change": zscore is not None and abs(zscore) >= ZSCORE_SIGNIFICANT,
            }
        )
    return series


def group_points(points: Sequence[LabPoint]) -> dict[str, list[LabPoint]]:
    grouped: dict[str, list[LabPoint]] = {}
    for point in points:
        grouped.setdefault(point.metric_key, []).append(point)
    return grouped


async def lab_points_for_patient(
    db: AsyncSession,
    patient_id: UUID,
    *,
    metrics: Optional[Sequence[str]] = None,
    since: Optional[date] = None,
    document_ids: Optional[Sequence[UUID]] = None,
) -> list[LabPoint]:
    result = await db.execute(patient_scoped_lab_query(patient_id, document_ids=document_ids))
    wanted = {m.strip().lower() for m in metrics or [] if m and m.strip()}
    points: list[LabPoint] = []
    for field_row, document in result.all():
        point = build_point(field_row, document)
        if not point:
            continue
        if wanted and point.metric_key not in wanted:
            continue
        if since and point.observed < since:
            continue
        points.append(point)
    return points


async def apply_flags(db: AsyncSession, document_id: UUID) -> int:
    result = await db.execute(
        select(ExtractedField).where(
            ExtractedField.document_id == document_id,
            ExtractedField.field_type == "lab",
        )
    )
    count = 0
    for field_row in result.scalars().all():
        field_row.flag = flag_field(field_row)
        count += 1
    await db.flush()
    return count


def compare_documents(
    current: Sequence[LabPoint], previous: Sequence[LabPoint]
) -> list[dict[str, Any]]:
    """Row per metric in the current report, against the same metric in the previous one."""
    prev_by_key = {p.metric_key: p for p in previous}
    rows: list[dict[str, Any]] = []
    for point in sorted(current, key=lambda p: (-FLAG_RANK.get(p.flag, 0), p.name)):
        prev = prev_by_key.get(point.metric_key)
        delta = point.value - prev.value if prev else None
        pct = (delta / prev.value * 100) if prev and prev.value else None
        rows.append(
            {
                "metric_key": point.metric_key,
                "name": point.name,
                "unit": point.unit,
                "value": point.value,
                "raw_value": point.raw_value,
                "flag": point.flag,
                "reference_low": point.reference.low,
                "reference_high": point.reference.high,
                "previous_value": prev.value if prev else None,
                "previous_flag": prev.flag if prev else None,
                "previous_date": prev.observed.isoformat() if prev else None,
                "delta": round(delta, 4) if delta is not None else None,
                "pct_change": round(pct, 2) if pct is not None else None,
                "direction": None
                if delta is None
                else "up" if delta > 0 else "down" if delta < 0 else "flat",
            }
        )
    return rows


def latest_before(points: Sequence[LabPoint], exclude_document_id: UUID) -> list[LabPoint]:
    """Most recent point per metric from other documents observed on/before this document."""
    own_dates = [p.observed for p in points if p.document_id == exclude_document_id]
    cutoff = max(own_dates) if own_dates else None
    best: dict[str, LabPoint] = {}
    for point in sorted(points, key=lambda p: p.observed):
        if point.document_id == exclude_document_id:
            continue
        if cutoff and point.observed > cutoff:
            continue
        best[point.metric_key] = point
    return list(best.values())


# --- API-facing helpers (access-checked) ---------------------------------------------------

_RANGE_DAYS = {"1m": 31, "3m": 92, "6m": 183, "1y": 366, "2y": 731, "5y": 1827}


def since_for_range(range_key: Optional[str], today: Optional[date] = None) -> Optional[date]:
    days = _RANGE_DAYS.get((range_key or "all").lower())
    if not days:
        return None
    return (today or date.today()) - timedelta(days=days)


async def resolve_document_scope(
    db: AsyncSession, user: User, patient_id: Optional[UUID]
) -> tuple[UUID, Optional[list[UUID]]]:
    """(patient_id, document_ids) the caller may read labs from; None means every document."""
    if user.role == UserRole.patient:
        if patient_id and patient_id != user.id:
            raise AppError("Patient not found", status_code=404, code="not_found")
        return user.id, None
    if user.role not in (UserRole.doctor, UserRole.caregiver) or not patient_id:
        raise AppError("Patient not found", status_code=404, code="not_found")
    full_patient_ids, document_ids = await granted_document_access(db, user)
    if patient_id in full_patient_ids:
        return patient_id, None
    if not document_ids:
        raise AppError("Patient not found", status_code=404, code="not_found")
    return patient_id, list(document_ids)


async def _audit_view(
    db: AsyncSession, user: User, patient_id: UUID, action: str, ip_address: Optional[str], **meta: Any
) -> None:
    if user.id == patient_id:
        return
    await write_audit_log(
        db,
        actor_id=user.id,
        action=action,
        resource_type="patient",
        resource_id=str(patient_id),
        ip_address=ip_address,
        metadata={"patient_id": str(patient_id), **meta},
    )


def _series_meta(points: Sequence[LabPoint]) -> dict[str, Any]:
    latest = max(points, key=lambda p: p.observed)
    return {
        "key": latest.metric_key,
        "name": latest.name,
        "unit": latest.unit,
        "reference_low": latest.reference.low,
        "reference_high": latest.reference.high,
    }


async def list_metrics(
    db: AsyncSession, user: User, patient_id: Optional[UUID], *, ip_address: Optional[str] = None
) -> list[dict[str, Any]]:
    pid, document_ids = await resolve_document_scope(db, user, patient_id)
    points = await lab_points_for_patient(db, pid, document_ids=document_ids)
    await _audit_view(db, user, pid, "trends.metrics_viewed", ip_address)
    metrics = []
    for key, group in group_points(points).items():
        latest = max(group, key=lambda p: p.observed)
        metrics.append(
            {
                "key": key,
                "name": latest.name,
                "unit": latest.unit,
                "point_count": len(group),
                "latest_value": latest.value,
                "latest_flag": latest.flag,
                "latest_date": latest.observed.isoformat(),
            }
        )
    return sorted(metrics, key=lambda m: (-m["point_count"], m["name"]))


async def get_trends(
    db: AsyncSession,
    user: User,
    patient_id: Optional[UUID],
    *,
    metrics: Sequence[str],
    range_key: Optional[str] = None,
    ip_address: Optional[str] = None,
) -> dict[str, Any]:
    pid, document_ids = await resolve_document_scope(db, user, patient_id)
    points = await lab_points_for_patient(
        db,
        pid,
        metrics=metrics or None,
        since=since_for_range(range_key),
        document_ids=document_ids,
    )
    await _audit_view(db, user, pid, "trends.viewed", ip_address, metrics=list(metrics))
    series = [
        {**_series_meta(group), "points": compute_series(group)}
        for group in group_points(points).values()
    ]
    return {"patient_id": pid, "series": sorted(series, key=lambda s: s["name"])}


async def compare_document(
    db: AsyncSession,
    user: User,
    document_id: UUID,
    *,
    against: Optional[UUID] = None,
    ip_address: Optional[str] = None,
) -> dict[str, Any]:
    from app.services.document_service import _get_accessible

    document = await _get_accessible(db, user, document_id)
    pid, document_ids = await _scope_for_document(db, user, document)
    points = await lab_points_for_patient(db, pid, document_ids=document_ids)
    current = [p for p in points if p.document_id == document.id]
    if against:
        previous = [p for p in points if p.document_id == against]
        if not previous:
            raise AppError("Comparison report not found", status_code=404, code="not_found")
    else:
        previous = latest_before(points, document.id)
    await _audit_view(db, user, pid, "trends.compared", ip_address, document_id=str(document.id))
    return {
        "document_id": document.id,
        "against_document_id": against,
        "rows": compare_documents(current, previous),
    }


async def _scope_for_document(
    db: AsyncSession, user: User, document: Any
) -> tuple[UUID, Optional[list[UUID]]]:
    try:
        return await resolve_document_scope(db, user, document.patient_id)
    except AppError:
        # Access to this one document was already verified; compare within it only.
        return document.patient_id, [document.id]
