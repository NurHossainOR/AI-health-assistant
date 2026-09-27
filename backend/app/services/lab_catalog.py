"""Canonical lab metrics: one key per test, with LOINC code, aliases and adult reference defaults.

Defaults apply only when a report omits its own reference range and the unit matches.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class LabMetric:
    key: str
    name: str
    loinc: Optional[str]
    unit: Optional[str]
    low: Optional[float] = None
    high: Optional[float] = None
    critical_low: Optional[float] = None
    critical_high: Optional[float] = None
    aliases: tuple[str, ...] = field(default_factory=tuple)


CATALOG: tuple[LabMetric, ...] = (
    LabMetric("ldl", "LDL Cholesterol", "13457-7", "mg/dL", high=130,
              aliases=("ldl", "ldl cholesterol", "ldl-c", "low density lipoprotein")),
    LabMetric("hdl", "HDL Cholesterol", "2085-9", "mg/dL", low=40,
              aliases=("hdl", "hdl cholesterol", "hdl-c", "high density lipoprotein")),
    LabMetric("triglycerides", "Triglycerides", "2571-8", "mg/dL", high=150, critical_high=500,
              aliases=("triglyceride", "triglycerides", "tg")),
    LabMetric("non_hdl", "Non-HDL Cholesterol", "43396-1", "mg/dL", high=130,
              aliases=("non-hdl", "non hdl", "non-hdl cholesterol", "non hdl cholesterol")),
    LabMetric("total_cholesterol", "Total Cholesterol", "2093-3", "mg/dL", high=200,
              aliases=("total cholesterol", "cholesterol total", "serum cholesterol")),
    LabMetric("hba1c", "Hemoglobin A1c", "4548-4", "%", low=4.0, high=5.6,
              aliases=("hba1c", "a1c", "hemoglobin a1c", "haemoglobin a1c", "glycated hemoglobin",
                       "glycosylated hemoglobin")),
    LabMetric("glucose", "Glucose", "2345-7", "mg/dL", low=70, high=99,
              critical_low=50, critical_high=400,
              aliases=("glucose", "fbs", "fbg", "fasting blood sugar", "fasting glucose",
                       "blood sugar", "rbs", "random blood sugar")),
    LabMetric("hemoglobin", "Hemoglobin", "718-7", "g/dL", low=12.0, high=17.5,
              critical_low=7.0, critical_high=20.0,
              aliases=("hemoglobin", "haemoglobin", "hb", "hgb")),
    LabMetric("hematocrit", "Hematocrit", "4544-3", "%", low=36, high=52,
              aliases=("hematocrit", "haematocrit", "hct", "pcv", "packed cell volume")),
    LabMetric("mcv", "MCV", "787-2", "fL", low=80, high=100,
              aliases=("mcv", "mean corpuscular volume", "mean cell volume")),
    LabMetric("mch", "MCH", "785-6", "pg", low=27, high=33,
              aliases=("mch", "mean corpuscular hemoglobin", "mean corpuscular haemoglobin",
                       "mean cell hemoglobin")),
    LabMetric("mchc", "MCHC", "786-4", "g/dL", low=32, high=36,
              aliases=("mchc", "mean corpuscular hemoglobin concentration",
                       "mean corpuscular haemoglobin concentration")),
    LabMetric("wbc", "WBC", "6690-2", "10^3/uL", low=4.0, high=11.0,
              critical_low=2.0, critical_high=30.0,
              aliases=("wbc", "white blood cell", "white blood cells", "total leucocyte count",
                       "total leukocyte count", "tlc", "total wbc count")),
    LabMetric("rbc", "RBC", "789-8", "10^6/uL", low=4.2, high=5.9,
              aliases=("rbc", "red blood cell", "red blood cells", "total rbc count")),
    LabMetric("platelets", "Platelets", "777-3", "10^3/uL", low=150, high=450,
              critical_low=50, critical_high=1000,
              aliases=("platelet", "platelets", "platelet count", "plt")),
    LabMetric("esr", "ESR", "4537-7", "mm/hr", high=20,
              aliases=("esr", "erythrocyte sedimentation rate")),
    LabMetric("creatinine", "Creatinine", "2160-0", "mg/dL", low=0.6, high=1.3,
              aliases=("creatinine", "serum creatinine", "s. creatinine")),
    LabMetric("urea", "Urea", "3091-6", "mg/dL", low=15, high=45,
              aliases=("urea", "blood urea", "serum urea")),
    LabMetric("sodium", "Sodium", "2951-2", "mmol/L", low=135, high=145,
              critical_low=120, critical_high=160, aliases=("sodium", "na", "serum sodium")),
    LabMetric("potassium", "Potassium", "2823-3", "mmol/L", low=3.5, high=5.1,
              critical_low=2.5, critical_high=6.5, aliases=("potassium", "k", "serum potassium")),
    LabMetric("alt", "ALT", "1742-6", "U/L", high=41,
              aliases=("alt", "sgpt", "alanine aminotransferase")),
    LabMetric("ast", "AST", "1920-8", "U/L", high=40,
              aliases=("ast", "sgot", "aspartate aminotransferase")),
    LabMetric("tsh", "TSH", "3016-3", "mIU/L", low=0.4, high=4.0,
              aliases=("tsh", "thyroid stimulating hormone")),
    LabMetric("vitamin_d", "Vitamin D (25-OH)", "1989-3", "ng/mL", low=30, high=100,
              aliases=("vitamin d", "25-oh vitamin d", "25 hydroxy vitamin d", "vit d")),
)

BY_KEY: dict[str, LabMetric] = {m.key: m for m in CATALOG}
BY_LOINC: dict[str, LabMetric] = {m.loinc: m for m in CATALOG if m.loinc}

# Longest alias first so "hemoglobin a1c" wins over "hemoglobin" and "mchc" over "mch".
_ALIASES: list[tuple[str, LabMetric]] = sorted(
    ((alias, m) for m in CATALOG for alias in m.aliases),
    key=lambda item: -len(item[0]),
)
# Very short aliases ("k", "na", "hb") only match exactly, never inside a longer name.
_ALIAS_PATTERNS: list[tuple[re.Pattern[str], LabMetric]] = [
    (re.compile(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])"), m)
    for alias, m in _ALIASES
    if len(alias) >= 3
]


def _normalize_name(name: str) -> str:
    return " ".join(re.sub(r"[_()\[\],:]", " ", name.lower()).split())


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "unknown"


def lookup(name: str, canonical_code: Optional[str] = None) -> Optional[LabMetric]:
    if canonical_code and canonical_code.strip() in BY_LOINC:
        return BY_LOINC[canonical_code.strip()]
    normalized = _normalize_name(name or "")
    if not normalized:
        return None
    for alias, metric in _ALIASES:
        if normalized == alias:
            return metric
    for pattern, metric in _ALIAS_PATTERNS:
        if pattern.search(normalized):
            return metric
    return None


def canonical_key(name: str, canonical_code: Optional[str] = None) -> str:
    metric = lookup(name, canonical_code)
    return metric.key if metric else slug(name)


def normalize_unit(unit: Optional[str]) -> str:
    return re.sub(r"\s+", "", (unit or "").lower()).replace("mgdl", "mg/dl")


def unit_compatible(metric: LabMetric, unit: Optional[str]) -> bool:
    """Catalog defaults only make sense in the catalog's unit (or when the report gives none)."""
    return not unit or not metric.unit or normalize_unit(unit) == normalize_unit(metric.unit)
