from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.user import ConsentScope, UserRole, UserStatus


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=255)
    role: UserRole = UserRole.patient
    bmdc_registration_number: Optional[str] = Field(default=None, max_length=20)
    specialty: Optional[str] = Field(default=None, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    mfa_code: Optional[str] = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    mfa_required: bool = False
    user: Optional["UserOut"] = None


class RefreshRequest(BaseModel):
    """Refresh can also come from httpOnly cookie; body is optional fallback."""

    refresh_token: Optional[str] = None


class MfaSetupResponse(BaseModel):
    secret: str
    otpauth_url: str
    qr_svg_data_uri: Optional[str] = None


class MfaVerifyRequest(BaseModel):
    code: str = Field(min_length=6, max_length=8)


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)


class EmailVerifyRequest(BaseModel):
    token: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    full_name: str
    role: UserRole
    status: UserStatus
    email_verified: bool
    mfa_enabled: bool
    created_at: datetime


class ConsentGrantCreate(BaseModel):
    grantee_id: UUID
    scope: ConsentScope = ConsentScope.all
    scope_detail: Optional[dict[str, Any]] = None
    expires_at: Optional[datetime] = None


class ConsentGrantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    patient_id: UUID
    grantee_id: UUID
    scope: ConsentScope
    scope_detail: Optional[dict[str, Any]] = None
    expires_at: Optional[datetime] = None
    granted_at: datetime
    revoked_at: Optional[datetime] = None
    grantee_name: Optional[str] = None
    patient_name: Optional[str] = None
    preview: Optional[dict[str, Any]] = None


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    actor_id: Optional[UUID]
    action: str
    resource_type: str
    resource_id: Optional[str]
    ip_address: Optional[str]
    metadata: Optional[dict[str, Any]] = Field(default=None, validation_alias="metadata_")
    created_at: datetime


class AdminUserOut(UserOut):
    bmdc_registration_number: Optional[str] = None
    specialty: Optional[str] = None
    verified_at: Optional[datetime] = None


class PipelineHealthOut(BaseModel):
    total: int
    pending: int
    running: int
    succeeded: int
    failed: int
    retrying: int
    recent_failures: list[dict[str, Any]]


class MessageOut(BaseModel):
    message: str
