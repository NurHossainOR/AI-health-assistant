from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import client_ip, get_current_user, get_current_user_optional
from app.core.config import get_settings
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import (
    EmailVerifyRequest,
    LoginRequest,
    MessageOut,
    MfaSetupResponse,
    MfaVerifyRequest,
    PasswordResetConfirm,
    PasswordResetRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserOut,
)
from app.services import auth_service
from app.services.auth_service import REFRESH_COOKIE

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=refresh_token,
        httponly=True,
        secure=not settings.debug,
        samesite="lax",
        max_age=settings.refresh_token_expire_days * 24 * 3600,
        path="/api/v1/auth",
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(key=REFRESH_COOKIE, path="/api/v1/auth")


@router.post("/register", response_model=MessageOut)
async def register(
    body: RegisterRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MessageOut:
    user, _ = await auth_service.register_user(db, body, ip_address=client_ip(request))
    msg = "Account created. Check your email to verify."
    if user.role.value == "doctor":
        msg += " Doctor accounts require admin verification after email confirmation."
    return MessageOut(message=msg)


@router.post("/verify-email", response_model=MessageOut)
async def verify_email(
    body: EmailVerifyRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MessageOut:
    await auth_service.verify_email(db, body.token)
    return MessageOut(message="Email verified successfully.")


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    result = await auth_service.login_user(db, body, ip_address=client_ip(request))
    if result.mfa_required:
        return result
    refresh = getattr(result, "_refresh_token", None)
    if refresh:
        _set_refresh_cookie(response, refresh)
    return result


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    body: Optional[RefreshRequest] = None,
) -> TokenResponse:
    token = request.cookies.get(REFRESH_COOKIE)
    if not token and body:
        token = body.refresh_token
    if not token:
        from app.core.exceptions import AppError

        raise AppError("Missing refresh token", status_code=401, code="missing_refresh")
    result = await auth_service.refresh_tokens(db, token, ip_address=client_ip(request))
    new_refresh = getattr(result, "_refresh_token", None)
    if new_refresh:
        _set_refresh_cookie(response, new_refresh)
    return result


@router.post("/logout", response_model=MessageOut)
async def logout(
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[Optional[User], Depends(get_current_user_optional)],
) -> MessageOut:
    token = request.cookies.get(REFRESH_COOKIE)
    uid = user.id if user else None
    await auth_service.logout_user(db, token, uid)
    _clear_refresh_cookie(response)
    return MessageOut(message="Logged out.")


@router.post("/mfa/setup", response_model=MfaSetupResponse)
async def mfa_setup(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> MfaSetupResponse:
    secret, otpauth, qr = await auth_service.setup_mfa(db, user)
    return MfaSetupResponse(secret=secret, otpauth_url=otpauth, qr_svg_data_uri=qr)


@router.post("/mfa/verify", response_model=MessageOut)
async def mfa_verify(
    body: MfaVerifyRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> MessageOut:
    await auth_service.verify_mfa_setup(db, user, body.code)
    return MessageOut(message="MFA enabled.")


@router.post("/password-reset", response_model=MessageOut)
async def password_reset(
    body: PasswordResetRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MessageOut:
    await auth_service.request_password_reset(db, body.email, ip_address=client_ip(request))
    return MessageOut(message="If that email exists, a reset link has been sent.")


@router.post("/password-reset/confirm", response_model=MessageOut)
async def password_reset_confirm(
    body: PasswordResetConfirm,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MessageOut:
    await auth_service.confirm_password_reset(db, body.token, body.new_password)
    return MessageOut(message="Password updated. Please log in.")


@router.get("/me", response_model=UserOut)
async def me(user: Annotated[User, Depends(get_current_user)]) -> UserOut:
    return UserOut.model_validate(user)
