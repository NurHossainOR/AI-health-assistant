from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import AuditLog

logger = logging.getLogger(__name__)


async def write_audit_log(
    db: AsyncSession,
    *,
    actor_id: Optional[UUID],
    action: str,
    resource_type: str,
    resource_id: Optional[str] = None,
    ip_address: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> AuditLog:
    entry = AuditLog(
        actor_id=actor_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        ip_address=ip_address,
        metadata_=metadata,
        created_at=datetime.now(timezone.utc),
    )
    db.add(entry)
    await db.flush()
    logger.info(
        "audit action=%s resource=%s/%s actor=%s",
        action,
        resource_type,
        resource_id,
        actor_id,
    )
    return entry
