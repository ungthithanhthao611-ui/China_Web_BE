from fastapi import APIRouter, Depends, File, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_admin_user
from app.services.media import create_uploaded_media_asset

router = APIRouter(prefix="/upload", tags=["upload"], dependencies=[Depends(require_admin_user)])


@router.post("/image", status_code=status.HTTP_201_CREATED)
async def upload_image(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> dict:
    payload = await create_uploaded_media_asset(
        db=db,
        file=file,
        title=file.filename,
        alt_text=file.filename,
        asset_folder="admin/avatars",
        public_id_base="admin-avatar",
    )
    return {
        "url": payload.get("url"),
        "id": payload.get("id"),
        "asset_type": payload.get("asset_type"),
        "fallback_reason": payload.get("fallback_reason"),
    }
