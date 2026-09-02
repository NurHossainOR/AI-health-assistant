from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from io import BytesIO
from typing import Optional
from uuid import UUID

import pyotp
import qrcode
import qrcode.image.svg
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    create_signed_token,
    decode_token,
    hash_password,
    verify_password,
    verify_signed_token,
)
from app.models.user import (
    DoctorProfile,
    PatientProfile,
    RefreshToken,
    User,
    UserRole,
    UserStatus,
)
from app.schemas.auth import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserOut,
)
from app.services.audit_service import write_audit_log
from app.services import email_service

REFRESH_COOKIE = "refresh_token"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
    result = await db.execute(select(User).where(User.email == email.lower()))
    return result.scalar_one_or_none()


async def get_user_by_id(db: AsyncSession, user_id: UUID) -> Optional[User]:
    result = await db.execute(
        select(User)
        .options(selectinload(User.doctor_profile), selectinload(User.patient_profile))
        .where(User.id == user_id)
    )
    return result.scalar_one_or_none()


async def register_user(
    db: AsyncSession,
    data: RegisterRequest,
    *,
    ip_address: Optional[str] = None,
) -> User:
    email_service.require_mailer()
    existing = await get_user_by_email(db, data.email)
    if existing:
        raise AppError("Email already registered", status_code=409, code="email_taken")

    if data.role == UserRole.admin:
        raise AppError("Cannot self-register as admin", status_code=400, code="invalid_role")

    status = UserStatus.pending_email
    if data.role == UserRole.doctor:
        status = UserStatus.pending_verification

    user = User(
        email=data.email.lower(),
        password_hash=hash_password(data.password),
        full_name=data.full_name,
        role=data.role,
        status=status,
        email_verified=False,
    )
    db.add(user)
    await db.flush()

    if data.role == UserRole.patient:
        db.add(PatientProfile(user_id=user.id))
    elif data.role == UserRole.doctor:
        db.add(
            DoctorProfile(
                user_id=user.id,
                bmdc_registration_number=data.bmdc_registration_number,
                specialty=data.specialty,
            )
        )
    elif data.role == UserRole.caregiver:
        # Caregiver has no dedicated profile table in v1
        pass

    verify_token = create_signed_token("email_verify", str(user.id), expires_minutes=60 * 24)
    settings = get_settings()
    verify_url = f"{settings.frontend_url}/verify-email?token={verify_token}"
    await email_service.send_verification_email(user.email, user.full_name, verify_url)

    await write_audit_log(
        db,
        actor_id=user.id,
        action="user.register",
        resource_type="user",
        resource_id=str(user.id),
        ip_address=ip_address,
        metadata={"role": user.role.value, "status": user.status.value},
    )
    return user


async def resend_verification_email(_db: AsyncSession, user: User) -> None:
    if user.email_verified:
        raise AppError("Email is already verified", status_code=400, code="already_verified")
    email_service.require_mailer()
    token = create_signed_token("email_verify", str(user.id), expires_minutes=60 * 24)
    settings = get_settings()
    verify_url = f"{settings.frontend_url}/verify-email?token={token}"
    await email_service.send_verification_email(user.email, user.full_name, verify_url)


async def verify_email(db: AsyncSession, token: str) -> User:
    try:
        user_id = UUID(verify_signed_token(token, "email_verify"))
    except ValueError as exc:
        raise AppError(str(exc), status_code=400, code="invalid_token") from exc

    user = await get_user_by_id(db, user_id)
    if not user:
        raise AppError("User not found", status_code=404)

    user.email_verified = True
    if user.role != UserRole.doctor:
        user.status = UserStatus.active
    # Doctors stay pending_verification until admin approves
    await db.flush()
    return user


async def _issue_tokens(db: AsyncSession, user: User) -> tuple[str, str, int]:
    settings = get_settings()
    jti = secrets.token_urlsafe(24)
    family_id = secrets.token_urlsafe(16)
    access = create_access_token(user.id, user.role.value)
    refresh = create_refresh_token(user.id, jti=jti, family_id=family_id)
    db.add(
        RefreshToken(
            user_id=user.id,
            jti=jti,
            family_id=family_id,
            expires_at=_utcnow() + timedelta(days=settings.refresh_token_expire_days),
        )
    )
    await db.flush()
    return access, refresh, settings.access_token_expire_minutes * 60


async def login_user(
    db: AsyncSession,
    data: LoginRequest,
    *,
    ip_address: Optional[str] = None,
) -> TokenResponse:
    user = await get_user_by_email(db, data.email)
    if not user or not verify_password(data.password, user.password_hash):
        await write_audit_log(
            db,
            actor_id=None,
            action="auth.login_failed",
            resource_type="user",
            resource_id=data.email.lower(),
            ip_address=ip_address,
        )
        raise AppError("Invalid email or password", status_code=401, code="invalid_credentials")

    if user.status == UserStatus.suspended:
        raise AppError("Account suspended", status_code=403, code="suspended")

    if user.mfa_enabled:
        if not data.mfa_code:
            return TokenResponse(
                access_token="",
                expires_in=0,
                mfa_required=True,
                user=UserOut.model_validate(user),
            )
        if not user.mfa_secret or not pyotp.TOTP(user.mfa_secret).verify(
            data.mfa_code, valid_window=1
        ):
            raise AppError("Invalid MFA code", status_code=401, code="invalid_mfa")

    access, refresh, expires_in = await _issue_tokens(db, user)
    await write_audit_log(
        db,
        actor_id=user.id,
        action="auth.login",
        resource_type="user",
        resource_id=str(user.id),
        ip_address=ip_address,
    )
    # Attach refresh via response cookie in route; return access here
    resp = TokenResponse(
        access_token=access,
        expires_in=expires_in,
        mfa_required=False,
        user=UserOut.model_validate(user),
    )
    # Stash refresh on object for route (not serialized)
    resp._refresh_token = refresh  # type: ignore[attr-defined]
    return resp


async def refresh_tokens(
    db: AsyncSession,
    refresh_token: str,
    *,
    ip_address: Optional[str] = None,
) -> TokenResponse:
    settings = get_settings()
    try:
        payload = decode_token(refresh_token)
    except JWTError as exc:
        raise AppError("Invalid refresh token", status_code=401, code="invalid_refresh") from exc

    if payload.get("type") != "refresh":
        raise AppError("Invalid refresh token", status_code=401, code="invalid_refresh")

    jti = payload.get("jti")
    family_id = payload.get("family_id")
    user_id = payload.get("sub")
    if not jti or not family_id or not user_id:
        raise AppError("Invalid refresh token", status_code=401, code="invalid_refresh")

    result = await db.execute(select(RefreshToken).where(RefreshToken.jti == jti))
    stored = result.scalar_one_or_none()

    # Reuse of revoked/missing token → revoke entire family (theft signal)
    if not stored or stored.revoked_at is not None:
        await _revoke_family(db, family_id)
        await write_audit_log(
            db,
            actor_id=UUID(user_id) if user_id else None,
            action="auth.refresh_reuse_detected",
            resource_type="refresh_token",
            resource_id=family_id,
            ip_address=ip_address,
        )
        raise AppError(
            "Refresh token reuse detected; session revoked",
            status_code=401,
            code="token_reuse",
        )

    if stored.expires_at.replace(tzinfo=timezone.utc) < _utcnow():
        stored.revoked_at = _utcnow()
        raise AppError("Refresh token expired", status_code=401, code="expired_refresh")

    user = await get_user_by_id(db, UUID(user_id))
    if not user or user.status == UserStatus.suspended:
        raise AppError("User not found or suspended", status_code=401)

    # Rotate
    new_jti = secrets.token_urlsafe(24)
    stored.revoked_at = _utcnow()
    stored.replaced_by_jti = new_jti
    db.add(
        RefreshToken(
            user_id=user.id,
            jti=new_jti,
            family_id=family_id,
            expires_at=_utcnow() + timedelta(days=settings.refresh_token_expire_days),
        )
    )
    access = create_access_token(user.id, user.role.value)
    new_refresh = create_refresh_token(user.id, jti=new_jti, family_id=family_id)
    await db.flush()

    resp = TokenResponse(
        access_token=access,
        expires_in=settings.access_token_expire_minutes * 60,
        user=UserOut.model_validate(user),
    )
    resp._refresh_token = new_refresh  # type: ignore[attr-defined]
    return resp


async def _revoke_family(db: AsyncSession, family_id: str) -> None:
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.family_id == family_id,
            RefreshToken.revoked_at.is_(None),
        )
    )
    now = _utcnow()
    for token in result.scalars().all():
        token.revoked_at = now


async def logout_user(db: AsyncSession, refresh_token: Optional[str], user_id: Optional[UUID]) -> None:
    if not refresh_token:
        return
    try:
        payload = decode_token(refresh_token)
        jti = payload.get("jti")
        if jti:
            result = await db.execute(select(RefreshToken).where(RefreshToken.jti == jti))
            stored = result.scalar_one_or_none()
            if stored and stored.revoked_at is None:
                stored.revoked_at = _utcnow()
    except JWTError:
        pass
    if user_id:
        await write_audit_log(
            db,
            actor_id=user_id,
            action="auth.logout",
            resource_type="user",
            resource_id=str(user_id),
        )


async def setup_mfa(db: AsyncSession, user: User) -> tuple[str, str, str]:
    secret = pyotp.random_base32()
    user.mfa_secret = secret
    user.mfa_enabled = False  # enabled after verify
    await db.flush()

    settings = get_settings()
    totp = pyotp.TOTP(secret)
    otpauth = totp.provisioning_uri(name=user.email, issuer_name=settings.app_name)

    img = qrcode.make(otpauth, image_factory=qrcode.image.svg.SvgImage)
    buf = BytesIO()
    img.save(buf)
    svg = buf.getvalue().decode("utf-8")
    data_uri = "data:image/svg+xml;utf8," + svg.replace("\n", "")
    return secret, otpauth, data_uri


async def verify_mfa_setup(db: AsyncSession, user: User, code: str) -> User:
    if not user.mfa_secret:
        raise AppError("MFA not initialized; call setup first", status_code=400)
    if not pyotp.TOTP(user.mfa_secret).verify(code, valid_window=1):
        raise AppError("Invalid MFA code", status_code=400, code="invalid_mfa")
    user.mfa_enabled = True
    await db.flush()
    await write_audit_log(
        db,
        actor_id=user.id,
        action="auth.mfa_enabled",
        resource_type="user",
        resource_id=str(user.id),
    )
    return user


async def request_password_reset(
    db: AsyncSession, email: str, *, ip_address: Optional[str] = None
) -> None:
    email_service.require_mailer()
    user = await get_user_by_email(db, email)
    # Always succeed to avoid email enumeration
    if not user:
        return
    token = create_signed_token("password_reset", str(user.id), expires_minutes=60)
    settings = get_settings()
    reset_url = f"{settings.frontend_url}/reset-password?token={token}"
    await email_service.send_password_reset_email(user.email, user.full_name, reset_url)
    await write_audit_log(
        db,
        actor_id=user.id,
        action="auth.password_reset_requested",
        resource_type="user",
        resource_id=str(user.id),
        ip_address=ip_address,
    )


async def confirm_password_reset(db: AsyncSession, token: str, new_password: str) -> User:
    try:
        user_id = UUID(verify_signed_token(token, "password_reset"))
    except ValueError as exc:
        raise AppError(str(exc), status_code=400, code="invalid_token") from exc

    user = await get_user_by_id(db, user_id)
    if not user:
        raise AppError("User not found", status_code=404)

    user.password_hash = hash_password(new_password)
    # Revoke all refresh tokens
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.user_id == user.id,
            RefreshToken.revoked_at.is_(None),
        )
    )
    now = _utcnow()
    for t in result.scalars().all():
        t.revoked_at = now
    await db.flush()
    await write_audit_log(
        db,
        actor_id=user.id,
        action="auth.password_reset",
        resource_type="user",
        resource_id=str(user.id),
    )
    return user
