from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from app.core.config import settings
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.schemas.user import UserCreate, UserLoginRequest, UserRead, UserTokenResponse


def register_user(db: Session, payload: UserCreate) -> User:
    # Check if email exists
    existing_user = db.scalar(select(User).where(User.email == payload.email))
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    # Check if username exists
    if payload.username:
        existing_username = db.scalar(select(User).where(User.username == payload.username))
        if existing_username:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already taken",
            )

    new_user = User(
        email=payload.email,
        username=payload.username,
        full_name=payload.full_name,
        phone=payload.phone,
        address=payload.address,
        password_hash=hash_password(payload.password),
        is_active=True,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user


def authenticate_user(db: Session, payload: UserLoginRequest) -> UserTokenResponse:
    user = db.scalar(select(User).where(User.email == payload.email))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is disabled",
        )

    user.last_login_at = datetime.now(timezone.utc)
    db.add(user)
    db.commit()
    db.refresh(user)

    access_token = create_access_token(
        subject=str(user.id),
        role="user",
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
    )
    return UserTokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.access_token_expire_minutes * 60,
        user=UserRead.model_validate(user, from_attributes=True),
    )
