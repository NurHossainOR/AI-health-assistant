from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class TrendMetricOut(BaseModel):
    key: str
    name: str
    unit: Optional[str] = None
    point_count: int
    latest_value: Optional[float] = None
    latest_flag: Optional[str] = None
    latest_date: Optional[str] = None


class TrendPointOut(BaseModel):
    date: str
    value: float
    raw_value: str
    unit: Optional[str] = None
    flag: str
    reference_low: Optional[float] = None
    reference_high: Optional[float] = None
    document_id: UUID
    document_name: str
    previous: Optional[float] = None
    delta: Optional[float] = None
    pct_change: Optional[float] = None
    direction: Optional[str] = None
    zscore: Optional[float] = None
    significant_change: bool = False


class TrendSeriesOut(BaseModel):
    key: str
    name: str
    unit: Optional[str] = None
    reference_low: Optional[float] = None
    reference_high: Optional[float] = None
    points: list[TrendPointOut]


class TrendsOut(BaseModel):
    patient_id: UUID
    series: list[TrendSeriesOut]


class CompareRowOut(BaseModel):
    metric_key: str
    name: str
    unit: Optional[str] = None
    value: float
    raw_value: str
    flag: str
    reference_low: Optional[float] = None
    reference_high: Optional[float] = None
    previous_value: Optional[float] = None
    previous_flag: Optional[str] = None
    previous_date: Optional[str] = None
    delta: Optional[float] = None
    pct_change: Optional[float] = None
    direction: Optional[str] = None


class CompareOut(BaseModel):
    document_id: UUID
    against_document_id: Optional[UUID] = None
    rows: list[CompareRowOut]
