from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.admin import AdminUser
from app.schemas.auth import AdminProfileUpdateRequest, AdminUserRead


def _profile_payload(user: AdminUser) -> dict:
    payload = AdminUserRead.model_validate(user, from_attributes=True).model_dump(mode="json")
    payload["status"] = "active" if user.is_active else "inactive"
    return payload


def get_admin_profile(current_user: AdminUser) -> dict:
    return _profile_payload(current_user)


def update_admin_profile(db: Session, current_user: AdminUser, payload: AdminProfileUpdateRequest) -> dict:
    normalized_username = payload.username.strip()
    if normalized_username != current_user.username:
        existing_user = db.scalar(select(AdminUser).where(AdminUser.username == normalized_username))
        if existing_user and existing_user.id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Username already exists.",
            )
        current_user.username = normalized_username

    normalized_email = str(payload.email or "").strip() or None
    if normalized_email:
        existing_email = db.scalar(select(AdminUser).where(AdminUser.email == normalized_email))
        if existing_email and existing_email.id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already exists.",
            )
    current_user.email = normalized_email
    current_user.phone = str(payload.phone or "").strip() or None
    current_user.avatar_url = str(payload.avatar_url or "").strip() or None

    db.add(current_user)
    db.commit()
    db.refresh(current_user)
    return _profile_payload(current_user)
