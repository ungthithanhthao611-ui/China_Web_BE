from datetime import datetime

from pydantic import BaseModel, EmailStr, field_validator


class AdminLoginRequest(BaseModel):
    username: str
    password: str


class AdminUserRead(BaseModel):
    id: int
    username: str
    email: EmailStr | None = None
    phone: str | None = None
    avatar_url: str | None = None
    role: str
    is_active: bool
    last_login_at: datetime | None = None


class AdminProfileUpdateRequest(BaseModel):
    username: str
    email: EmailStr | None = None
    phone: str | None = None
    avatar_url: str | None = None

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        normalized = str(value or "").strip()
        if len(normalized) < 3:
            raise ValueError("Username must contain at least 3 characters.")
        return normalized

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        if not normalized:
            return None
        digits = "".join(ch for ch in normalized if ch.isdigit())
        if len(digits) < 10:
            raise ValueError("Phone number must contain at least 10 digits.")
        return normalized


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: AdminUserRead
