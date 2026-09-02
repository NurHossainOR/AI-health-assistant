from __future__ import annotations

from app.workers.celery_app import celery_app
from app.workers import ingestion  # noqa: F401

__all__ = ["celery_app"]
