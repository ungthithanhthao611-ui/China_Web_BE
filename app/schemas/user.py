from datetime import datetime
from pydantic import BaseModel, EmailStr, Field


class UserBase(BaseModel):
    email: EmailStr
    username: str | None = None
    full_name: str | None = None
    phone: str | None = None
    address: str | None = None


class UserCreate(UserBase):
    password: str = Field(..., min_length=6)


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    username: str | None = None
    full_name: str | None = None
    phone: str | None = None
    address: str | None = None
    password: str | None = Field(None, min_length=6)


class UserRead(UserBase):
    id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime | None = None
    last_login_at: datetime | None = None

    class Config:
        from_attributes = True


class UserLoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserRead
