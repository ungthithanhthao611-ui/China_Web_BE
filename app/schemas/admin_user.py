from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

class AdminUserBase(BaseModel):
    username: str
    email: EmailStr | None = None
    phone: str | None = None
    avatar_url: str | None = None
    role: str = "admin"
    is_active: bool = True

class AdminUserCreate(AdminUserBase):
    password: str = Field(..., min_length=6)

class AdminUserUpdate(BaseModel):
    username: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    avatar_url: str | None = None
    role: str | None = None
    is_active: bool | None = None
    password: str | None = Field(None, min_length=6)

class AdminUserRead(AdminUserBase):
    id: int
    last_login_at: datetime | None = None
    created_at: datetime
    updated_at: datetime | None = None

    class Config:
        from_attributes = True
