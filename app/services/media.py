from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.media import MediaAsset
from app.schemas.entities import MediaAssetRead

ALLOWED_UPLOAD_MIME_PREFIXES = ("image/", "video/")
ALLOWED_UPLOAD_MIME_TYPES = {"application/pdf"}


def _asset_type_from_mime_type(mime_type: str | None) -> str:
    if not mime_type:
        return "file"
    if mime_type.startswith("image/"):
        return "image"
    if mime_type.startswith("video/"):
        return "video"
    if mime_type == "application/pdf":
        return "document"
    return "file"


def _safe_extension(filename: str | None) -> str:
    suffix = Path(filename or "").suffix.lower()
    if not suffix or len(suffix) > 12:
        return ""
    return suffix


def _validate_mime_type(mime_type: str | None) -> None:
    if not mime_type:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is missing a content type.",
        )

    if mime_type in ALLOWED_UPLOAD_MIME_TYPES:
        return

    if any(mime_type.startswith(prefix) for prefix in ALLOWED_UPLOAD_MIME_PREFIXES):
        return

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Only image, video, and PDF uploads are allowed.",
    )


async def create_uploaded_media_asset(
    db: Session,
    file: UploadFile,
    title: str | None = None,
    alt_text: str | None = None,
) -> dict:
    _validate_mime_type(file.content_type)

    now = datetime.now(timezone.utc)
    date_path = now.strftime("%Y/%m/%d")
    upload_root = Path(settings.upload_dir)
    target_dir = upload_root / date_path
    target_dir.mkdir(parents=True, exist_ok=True)

    file_uuid = str(uuid4())
    target_name = f"{file_uuid}{_safe_extension(file.filename)}"
    target_path = target_dir / target_name
    max_size = settings.max_upload_size_mb * 1024 * 1024
    total_size = 0

    try:
        with target_path.open("wb") as output:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                total_size += len(chunk)
                if total_size > max_size:
                    output.close()
                    target_path.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"Uploaded file exceeds {settings.max_upload_size_mb}MB.",
                    )
                output.write(chunk)
    finally:
        await file.close()

    storage_path = str(target_path.as_posix())
    url = f"{settings.upload_url_prefix.rstrip('/')}/{date_path}/{target_name}"
    record = MediaAsset(
        uuid=file_uuid,
        file_name=file.filename,
        url=url,
        storage_path=storage_path,
        asset_type=_asset_type_from_mime_type(file.content_type),
        mime_type=file.content_type,
        size=total_size,
        alt_text=alt_text,
        title=title or file.filename,
        status="active",
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return MediaAssetRead.model_validate(record).model_dump(mode="json")
