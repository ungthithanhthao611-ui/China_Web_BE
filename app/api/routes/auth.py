from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin_user, get_db
from app.models.admin import AdminUser
from app.schemas.auth import AdminLoginRequest, AdminUserRead, TokenResponse
from app.services.auth import authenticate_admin_user

router = APIRouter()


@router.post("/login")
def login(payload: AdminLoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    return authenticate_admin_user(db=db, payload=payload)


@router.get("/me")
def me(current_user: AdminUser = Depends(get_current_admin_user)) -> AdminUserRead:
    return AdminUserRead.model_validate(current_user, from_attributes=True)
