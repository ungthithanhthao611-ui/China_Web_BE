from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin_user, get_db, require_admin_user
from app.models.admin import AdminUser
from app.schemas.auth import AdminProfileUpdateRequest
from app.services.admin_profile import get_admin_profile, update_admin_profile

router = APIRouter(prefix="/admin/profile", tags=["admin-profile"], dependencies=[Depends(require_admin_user)])


@router.get("")
def profile(current_user: AdminUser = Depends(get_current_admin_user)) -> dict:
    return get_admin_profile(current_user)


@router.put("")
def update_profile(
    payload: AdminProfileUpdateRequest,
    db: Session = Depends(get_db),
    current_user: AdminUser = Depends(get_current_admin_user),
) -> dict:
    return update_admin_profile(db=db, current_user=current_user, payload=payload)

