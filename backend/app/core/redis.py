from __future__ import annotations

import json
import logging
from typing import Optional
from uuid import UUID

from redis.asyncio import Redis

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_redis: Optional[Redis] = None


def get_redis() -> Redis:
    global _redis
    if _redis is None:
        _redis = Redis.from_url(get_settings().redis_url, decode_responses=True)
    return _redis


def status_channel(document_id: UUID | str) -> str:
    return f"docstatus:{document_id}"


async def publish_document_status(document_id: UUID | str, payload: dict) -> None:
    client: Optional[Redis] = None
    try:
        client = Redis.from_url(get_settings().redis_url, decode_responses=True)
        await client.publish(status_channel(document_id), json.dumps(payload))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Redis publish failed: %s", exc)
    finally:
        if client is not None:
            await client.aclose()
