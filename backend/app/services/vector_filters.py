from __future__ import annotations

from uuid import UUID


def patient_metadata_filter(patient_id: UUID | str) -> dict:
    """Mandatory Chroma where-clause. Retrieval must never omit this."""
    return {"patient_id": {"$eq": str(patient_id)}}
