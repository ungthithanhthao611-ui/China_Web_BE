from datetime import datetime, timezone
from pathlib import Path
import re
from uuid import uuid4

import cloudinary
import cloudinary.uploader
from fastapi import HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.content import Banner, ContentBlockItem, PageSection
from app.models.media import MediaAsset
from app.models.media import EntityMedia
from app.models.news import Post
from app.models.organization import Branch, Video
from app.models.projects import Project
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


def _slugify(value: str | None) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower())
    normalized = normalized.strip("-")
    return normalized or str(uuid4())


def _normalize_asset_folder(asset_folder: str | None) -> str | None:
    normalized = str(asset_folder or "").strip().strip("/")
    if not normalized:
        return None

    root_folder = settings.cloudinary_folder.strip().strip("/")
    if root_folder and normalized.lower().startswith(f"{root_folder.lower()}/"):
        return normalized
    if root_folder and normalized.lower() == root_folder.lower():
        return normalized
    return f"{root_folder}/{normalized}" if root_folder else normalized


def _media_response(
    record: MediaAsset,
    *,
    storage_backend: str,
    fallback_reason: str | None = None,
) -> dict:
    payload = MediaAssetRead.model_validate(record).model_dump(mode="json")
    payload["storage_backend"] = storage_backend
    if fallback_reason:
        payload["fallback_reason"] = fallback_reason
    return payload


def _storage_backend_for_record(record: MediaAsset) -> str:
    url = str(record.url or "")
    storage_path = str(record.storage_path or "")

    if "res.cloudinary.com/" in url:
        return "cloudinary"
    if url.startswith(settings.upload_url_prefix.rstrip("/")) or Path(storage_path).is_absolute():
        return "local"
    return "external"


def _cloudinary_resource_type(asset_type: str | None) -> str:
    if asset_type == "image":
        return "image"
    if asset_type == "video":
        return "video"
    return "raw"


def _delete_cloudinary_asset(record: MediaAsset) -> None:
    if not _has_cloudinary_configuration():
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Cloudinary credentials are unavailable for deleting this asset.",
        )

    _configure_cloudinary()
    public_id = str(record.storage_path or "").strip()
    if not public_id:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Media asset is missing Cloudinary public_id in storage_path.",
        )

    try:
        result = cloudinary.uploader.destroy(
            public_id,
            resource_type=_cloudinary_resource_type(record.asset_type),
            invalidate=True,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Cloudinary delete failed: {exc}",
        ) from exc

    outcome = str((result or {}).get("result") or "").lower()
    if outcome not in {"ok", "not found"}:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Cloudinary delete failed with result: {outcome or 'unknown'}",
        )


def _delete_local_asset(record: MediaAsset) -> None:
    storage_path = str(record.storage_path or "").strip()
    if not storage_path:
        return

    target = Path(storage_path)
    if target.exists():
        target.unlink(missing_ok=True)


def _media_asset_references(db: Session, media_id: int) -> list[str]:
    reference_checks = [
        ("banners.image_id", select(func.count()).select_from(Banner).where(Banner.image_id == media_id)),
        ("page_sections.image_id", select(func.count()).select_from(PageSection).where(PageSection.image_id == media_id)),
        (
            "content_block_items.image_id",
            select(func.count()).select_from(ContentBlockItem).where(ContentBlockItem.image_id == media_id),
        ),
        ("posts.image_id", select(func.count()).select_from(Post).where(Post.image_id == media_id)),
        ("projects.image_id", select(func.count()).select_from(Project).where(Project.image_id == media_id)),
        ("projects.hero_image_id", select(func.count()).select_from(Project).where(Project.hero_image_id == media_id)),
        ("videos.thumbnail_id", select(func.count()).select_from(Video).where(Video.thumbnail_id == media_id)),
        ("branches.image_id", select(func.count()).select_from(Branch).where(Branch.image_id == media_id)),
        ("branches.hero_image_id", select(func.count()).select_from(Branch).where(Branch.hero_image_id == media_id)),
        ("entity_media.media_id", select(func.count()).select_from(EntityMedia).where(EntityMedia.media_id == media_id)),
    ]

    references: list[str] = []
    for label, query in reference_checks:
        count = db.scalar(query) or 0
        if count:
            references.append(f"{label} ({count})")
    return references


def delete_media_asset_record(db: Session, record: MediaAsset) -> None:
    references = _media_asset_references(db, record.id)
    if references:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Media asset is still in use: {', '.join(references)}",
        )

    storage_backend = _storage_backend_for_record(record)
    if storage_backend == "cloudinary":
        _delete_cloudinary_asset(record)
    elif storage_backend == "local":
        _delete_local_asset(record)

    db.delete(record)
    db.commit()


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


def _has_cloudinary_configuration() -> bool:
    if settings.cloudinary_url.strip():
        return True
    return all(
        [
            settings.cloudinary_cloud_name.strip(),
            settings.cloudinary_api_key.strip(),
            settings.cloudinary_api_secret.strip(),
        ]
    )


def _configure_cloudinary() -> None:
    if settings.cloudinary_url:
        cloudinary.config(cloudinary_url=settings.cloudinary_url, secure=True)
        return

    if not settings.cloudinary_cloud_name or not settings.cloudinary_api_key or not settings.cloudinary_api_secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Cloudinary is not configured. Please set CLOUDINARY_URL or CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, and CLOUDINARY_API_SECRET.",
        )

    cloudinary.config(
        cloud_name=settings.cloudinary_cloud_name,
        api_key=settings.cloudinary_api_key,
        api_secret=settings.cloudinary_api_secret,
        secure=True,
    )


async def _create_cloudinary_media_asset(
    db: Session,
    file: UploadFile,
    title: str | None = None,
    alt_text: str | None = None,
    asset_folder: str | None = None,
    public_id_base: str | None = None,
) -> dict:
    _configure_cloudinary()

    raw_bytes = await file.read()
    max_size = settings.max_upload_size_mb * 1024 * 1024
    total_size = len(raw_bytes)
    if total_size > max_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Uploaded file exceeds {settings.max_upload_size_mb}MB.",
        )

    try:
        normalized_asset_folder = _normalize_asset_folder(asset_folder)
        public_id = _slugify(public_id_base or title or Path(file.filename or "").stem)
        upload_result = cloudinary.uploader.upload(
            raw_bytes,
            asset_folder=normalized_asset_folder,
            resource_type="auto",
            public_id=public_id,
            use_filename=False,
            unique_filename=False,
            overwrite=True,
            use_asset_folder_as_public_id_prefix=True,
            display_name=title or file.filename,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Cloudinary upload failed: {exc}",
        ) from exc

    record = MediaAsset(
        # Keep DB uuid independent from Cloudinary public_id so repeated uploads
        # with the same title/public_id do not violate uq_media_assets_uuid.
        uuid=str(uuid4()),
        file_name=file.filename,
        url=upload_result.get("secure_url") or upload_result.get("url"),
        storage_path=upload_result.get("public_id"),
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
    return _media_response(record, storage_backend="cloudinary")


async def _create_local_media_asset(
    db: Session,
    file: UploadFile,
    title: str | None = None,
    alt_text: str | None = None,
) -> dict:
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
    return _media_response(record, storage_backend="local")


async def create_uploaded_media_asset(
    db: Session,
    file: UploadFile,
    title: str | None = None,
    alt_text: str | None = None,
    asset_folder: str | None = None,
    public_id_base: str | None = None,
) -> dict:
    _validate_mime_type(file.content_type)

    try:
        if settings.media_storage.strip().lower() == "cloudinary":
            if not _has_cloudinary_configuration():
                local_payload = await _create_local_media_asset(db=db, file=file, title=title, alt_text=alt_text)
                local_payload["fallback_reason"] = "Cloudinary credentials are incomplete."
                return local_payload

            try:
                return await _create_cloudinary_media_asset(
                    db=db,
                    file=file,
                    title=title,
                    alt_text=alt_text,
                    asset_folder=asset_folder,
                    public_id_base=public_id_base,
                )
            except HTTPException as exc:
                # Keep hard validation errors, but gracefully degrade for Cloudinary infra/config failures.
                if exc.status_code not in {
                    status.HTTP_500_INTERNAL_SERVER_ERROR,
                    status.HTTP_502_BAD_GATEWAY,
                }:
                    raise
                await file.seek(0)
                local_payload = await _create_local_media_asset(db=db, file=file, title=title, alt_text=alt_text)
                local_payload["fallback_reason"] = str(exc.detail)
                return local_payload

        return await _create_local_media_asset(db=db, file=file, title=title, alt_text=alt_text)
    finally:
        await file.close()
