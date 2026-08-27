from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
ALGORITHM = "RS256"


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def create_access_token(
    subject: str | UUID,
    role: str,
    *,
    extra: Optional[dict[str, Any]] = None,
) -> str:
    settings = get_settings()
    expire = _utcnow() + timedelta(minutes=settings.access_token_expire_minutes)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "role": role,
        "type": "access",
        "exp": expire,
        "iat": _utcnow(),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.jwt_private_key, algorithm=ALGORITHM)


def create_refresh_token(
    subject: str | UUID,
    *,
    jti: str,
    family_id: str,
) -> str:
    settings = get_settings()
    expire = _utcnow() + timedelta(days=settings.refresh_token_expire_days)
    payload = {
        "sub": str(subject),
        "type": "refresh",
        "jti": jti,
        "family_id": family_id,
        "exp": expire,
        "iat": _utcnow(),
    }
    return jwt.encode(payload, settings.jwt_private_key, algorithm=ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    return jwt.decode(token, settings.jwt_public_key, algorithms=[ALGORITHM])


def create_signed_token(purpose: str, subject: str, expires_minutes: int = 60) -> str:
    """Signed expiring token for email verification / password reset."""
    settings = get_settings()
    expire = _utcnow() + timedelta(minutes=expires_minutes)
    payload = {
        "sub": subject,
        "purpose": purpose,
        "exp": expire,
        "iat": _utcnow(),
    }
    return jwt.encode(payload, settings.jwt_private_key, algorithm=ALGORITHM)


def verify_signed_token(token: str, purpose: str) -> str:
    try:
        payload = decode_token(token)
    except JWTError as exc:
        raise ValueError("Invalid or expired token") from exc
    if payload.get("purpose") != purpose:
        raise ValueError("Invalid token purpose")
    sub = payload.get("sub")
    if not sub:
        raise ValueError("Invalid token subject")
    return str(sub)
