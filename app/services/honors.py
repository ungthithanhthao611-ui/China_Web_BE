import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cloudinary
import cloudinary.uploader
from fastapi import HTTPException, status
from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.models.organization import Honor, HonorCategory
from app.schemas.honors import (
    HonorCategoryCreateDTO,
    HonorCategoryReadDTO,
    HonorCategoryUpdateDTO,
    HonorCreateDTO,
    HonorReadDTO,
    HonorToggleActiveDTO,
    HonorUpdateDTO,
)

DISPLAY_TYPES = {
    "qualification_certificate",
    "corporate_honors",
    "project_honors",
}

CLOUDINARY_URL_PREFIX = "https://res.cloudinary.com/"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _slugify(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", str(value).lower()).strip("-")
    return normalized or "honor-item"


def _category_payload(record: HonorCategory | None) -> dict[str, Any] | None:
    if not record:
        return None
    return HonorCategoryReadDTO.model_validate(record).model_dump(mode="json")


def _honor_payload(record: Honor) -> dict[str, Any]:
    payload = HonorReadDTO.model_validate(record).model_dump(mode="json")
    payload["category"] = _category_payload(record.category)
    return payload


def _ensure_unique_slug(
    db: Session,
    model: type[Honor] | type[HonorCategory],
    raw_slug: str | None,
    *,
    record_id: int | None = None,
) -> str:
    base_slug = _slugify(raw_slug or "")
    candidate = base_slug
    suffix = 2

    while True:
        query = select(model).where(model.slug == candidate)
        if hasattr(model, "deleted_at"):
            query = query.where(getattr(model, "deleted_at").is_(None))
        existing = db.scalar(query)
        if not existing or (record_id and existing.id == record_id):
            return candidate
        candidate = f"{base_slug}-{suffix}"
        suffix += 1


def _resolve_display_type(explicit_value: str | None, category: HonorCategory | None) -> str:
    if explicit_value and explicit_value in DISPLAY_TYPES:
        return explicit_value
    if not category:
        return "qualification_certificate"
    if category.slug == "qualification-certificate" or category.type == "qualification_certificate":
        return "qualification_certificate"
    if category.slug == "corporate-honors" or category.type == "corporate_honors":
        return "corporate_honors"
    if category.slug == "project-honors" or category.type == "project_honors":
        return "project_honors"
    if category.type in DISPLAY_TYPES:
        return category.type
    return "qualification_certificate"


def _get_honor_category(db: Session, category_id: int) -> HonorCategory:
    category = db.scalar(
        select(HonorCategory).where(HonorCategory.id == category_id, HonorCategory.deleted_at.is_(None))
    )
    if not category:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Honor category not found.")
    return category


def _ensure_no_parent_cycle(db: Session, *, category_id: int, parent_id: int) -> None:
    current_parent_id: int | None = parent_id
    visited: set[int] = set()

    while current_parent_id is not None:
        if current_parent_id == category_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Category parent hierarchy cannot contain cycles.",
            )
        if current_parent_id in visited:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Detected invalid category cycle.",
            )
        visited.add(current_parent_id)
        current_parent = _get_honor_category(db, current_parent_id)
        current_parent_id = current_parent.parent_id


def list_admin_honor_categories(
    db: Session,
    *,
    keyword: str | None,
    is_active: bool | None,
    include_deleted: bool,
) -> list[dict[str, Any]]:
    query = select(HonorCategory)
    if not include_deleted:
        query = query.where(HonorCategory.deleted_at.is_(None))
    if is_active is not None:
        query = query.where(HonorCategory.is_active == is_active)
    if keyword:
        pattern = f"%{keyword.strip()}%"
        query = query.where(
            or_(
                cast(HonorCategory.name, String).ilike(pattern),
                cast(HonorCategory.slug, String).ilike(pattern),
                cast(HonorCategory.type, String).ilike(pattern),
            )
        )

    items = db.scalars(query.order_by(HonorCategory.sort_order, HonorCategory.id)).all()
    return [_category_payload(item) for item in items]


def create_admin_honor_category(db: Session, payload: HonorCategoryCreateDTO) -> dict[str, Any]:
    parent = None
    if payload.parent_id:
        parent = _get_honor_category(db, payload.parent_id)
        if parent.deleted_at is not None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Parent category is deleted.")

    normalized_slug = _ensure_unique_slug(db, HonorCategory, payload.slug or payload.name)
    category = HonorCategory(
        name=payload.name.strip(),
        slug=normalized_slug,
        type=payload.type.strip(),
        parent_id=parent.id if parent else None,
        description=payload.description,
        sort_order=payload.sort_order,
        is_active=payload.is_active,
    )
    db.add(category)
    db.commit()
    db.refresh(category)
    return _category_payload(category)


def update_admin_honor_category(
    db: Session,
    category_id: int,
    payload: HonorCategoryUpdateDTO,
) -> dict[str, Any]:
    category = _get_honor_category(db, category_id)
    data = payload.model_dump(exclude_unset=True)

    if "parent_id" in data:
        parent_id = data["parent_id"]
        if parent_id == category.id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Category cannot be parent of itself.")
        if parent_id is None:
            category.parent_id = None
        else:
            parent = _get_honor_category(db, parent_id)
            _ensure_no_parent_cycle(db, category_id=category.id, parent_id=parent.id)
            category.parent_id = parent.id

    if "name" in data and data["name"] is not None:
        category.name = data["name"].strip()
    if "slug" in data and data["slug"] is not None:
        category.slug = _ensure_unique_slug(db, HonorCategory, data["slug"], record_id=category.id)
    if "type" in data and data["type"] is not None:
        category.type = data["type"].strip()
    if "description" in data:
        category.description = data["description"]
    if "sort_order" in data and data["sort_order"] is not None:
        category.sort_order = data["sort_order"]
    if "is_active" in data and data["is_active"] is not None:
        category.is_active = data["is_active"]

    db.add(category)
    db.commit()
    db.refresh(category)
    return _category_payload(category)


def soft_delete_admin_honor_category(db: Session, category_id: int) -> None:
    category = _get_honor_category(db, category_id)
    child_count = db.scalar(
        select(func.count())
        .select_from(HonorCategory)
        .where(HonorCategory.parent_id == category.id, HonorCategory.deleted_at.is_(None))
    )
    if child_count:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete category while child categories are still linked to it.",
        )

    in_use = db.scalar(
        select(func.count())
        .select_from(Honor)
        .where(Honor.category_id == category.id, Honor.deleted_at.is_(None))
    )
    if in_use:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete category while honors are still linked to it.",
        )

    category.deleted_at = _now()
    category.is_active = False
    db.add(category)
    db.commit()


def list_admin_honors(
    db: Session,
    *,
    skip: int,
    limit: int,
    category_id: int | None,
    keyword: str | None,
    is_active: bool | None,
    include_deleted: bool,
) -> dict[str, Any]:
    filters = []
    if not include_deleted:
        filters.append(Honor.deleted_at.is_(None))
    if category_id is not None:
        filters.append(Honor.category_id == category_id)
    if is_active is not None:
        filters.append(Honor.is_active == is_active)
    if keyword:
        pattern = f"%{keyword.strip()}%"
        filters.append(
            or_(
                cast(Honor.title, String).ilike(pattern),
                cast(Honor.slug, String).ilike(pattern),
                cast(Honor.short_description, String).ilike(pattern),
                cast(Honor.issued_by, String).ilike(pattern),
                cast(HonorCategory.name, String).ilike(pattern),
            )
        )

    base_query = (
        select(Honor)
        .outerjoin(HonorCategory, Honor.category_id == HonorCategory.id)
        .options(selectinload(Honor.category))
        .where(*filters)
    )
    count_query = select(func.count()).select_from(Honor).outerjoin(HonorCategory, Honor.category_id == HonorCategory.id).where(*filters)

    items = db.scalars(
        base_query.order_by(Honor.sort_order, Honor.year.desc().nullslast(), Honor.id.desc()).offset(skip).limit(limit)
    ).all()
    total = db.scalar(count_query) or 0

    return {
        "items": [_honor_payload(item) for item in items],
        "pagination": {"skip": skip, "limit": limit, "total": total},
    }


def get_admin_honor(db: Session, honor_id: int) -> dict[str, Any]:
    honor = db.scalar(
        select(Honor).options(selectinload(Honor.category)).where(Honor.id == honor_id, Honor.deleted_at.is_(None))
    )
    if not honor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Honor not found.")
    return _honor_payload(honor)


def create_admin_honor(db: Session, payload: HonorCreateDTO, *, actor_id: int | None) -> dict[str, Any]:
    category = _get_honor_category(db, payload.category_id) if payload.category_id else None
    slug = _ensure_unique_slug(db, Honor, payload.slug or payload.title)
    honor = Honor(
        category_id=category.id if category else None,
        title=payload.title.strip(),
        slug=slug,
        short_description=payload.short_description,
        image_url=payload.image_url,
        year=payload.year,
        issued_by=payload.issued_by,
        display_type=_resolve_display_type(payload.display_type, category),
        sort_order=payload.sort_order,
        is_featured=payload.is_featured,
        is_active=payload.is_active,
        created_by=actor_id,
        updated_by=actor_id,
    )
    db.add(honor)
    db.commit()
    db.refresh(honor)
    honor = db.scalar(select(Honor).options(selectinload(Honor.category)).where(Honor.id == honor.id))
    return _honor_payload(honor)


def update_admin_honor(
    db: Session,
    honor_id: int,
    payload: HonorUpdateDTO,
    *,
    actor_id: int | None,
) -> dict[str, Any]:
    honor = db.scalar(
        select(Honor).options(selectinload(Honor.category)).where(Honor.id == honor_id, Honor.deleted_at.is_(None))
    )
    if not honor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Honor not found.")

    data = payload.model_dump(exclude_unset=True)
    category = honor.category

    if "category_id" in data:
        category_id = data["category_id"]
        category = _get_honor_category(db, category_id) if category_id else None
        honor.category_id = category.id if category else None

    if "title" in data and data["title"] is not None:
        honor.title = data["title"].strip()
    if "slug" in data and data["slug"] is not None:
        honor.slug = _ensure_unique_slug(db, Honor, data["slug"], record_id=honor.id)
    if "short_description" in data:
        honor.short_description = data["short_description"]
    if "image_url" in data:
        honor.image_url = data["image_url"]
    if "year" in data:
        honor.year = data["year"]
    if "issued_by" in data:
        honor.issued_by = data["issued_by"]
    if "sort_order" in data and data["sort_order"] is not None:
        honor.sort_order = data["sort_order"]
    if "is_featured" in data and data["is_featured"] is not None:
        honor.is_featured = data["is_featured"]
    if "is_active" in data and data["is_active"] is not None:
        honor.is_active = data["is_active"]

    if "display_type" in data:
        honor.display_type = _resolve_display_type(data["display_type"], category)
    elif "category_id" in data:
        honor.display_type = _resolve_display_type(honor.display_type, category)

    honor.updated_by = actor_id
    db.add(honor)
    db.commit()
    db.refresh(honor)
    honor = db.scalar(select(Honor).options(selectinload(Honor.category)).where(Honor.id == honor.id))
    return _honor_payload(honor)


def soft_delete_admin_honor(db: Session, honor_id: int, *, actor_id: int | None) -> None:
    honor = db.scalar(select(Honor).where(Honor.id == honor_id, Honor.deleted_at.is_(None)))
    if not honor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Honor not found.")

    honor.deleted_at = _now()
    honor.is_active = False
    honor.updated_by = actor_id
    db.add(honor)
    db.commit()


def toggle_admin_honor_active(
    db: Session,
    honor_id: int,
    payload: HonorToggleActiveDTO,
    *,
    actor_id: int | None,
) -> dict[str, Any]:
    honor = db.scalar(
        select(Honor).options(selectinload(Honor.category)).where(Honor.id == honor_id, Honor.deleted_at.is_(None))
    )
    if not honor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Honor not found.")
    honor.is_active = payload.is_active
    honor.updated_by = actor_id
    db.add(honor)
    db.commit()
    db.refresh(honor)
    return _honor_payload(honor)


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
    if settings.cloudinary_url.strip():
        cloudinary.config(cloudinary_url=settings.cloudinary_url, secure=True)
        return

    if not _has_cloudinary_configuration():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Cloudinary credentials are incomplete.",
        )

    cloudinary.config(
        cloud_name=settings.cloudinary_cloud_name,
        api_key=settings.cloudinary_api_key,
        api_secret=settings.cloudinary_api_secret,
        secure=True,
    )


def _resolve_upload_source(image_url: str) -> str:
    normalized = image_url.strip()
    if not normalized:
        raise ValueError("Empty image URL.")

    if normalized.startswith(CLOUDINARY_URL_PREFIX):
        return normalized

    if normalized.startswith("/uploads/"):
        relative_part = normalized.removeprefix("/uploads/").strip("/")
        local_path = Path(settings.upload_dir) / relative_part
        if not local_path.exists():
            raise ValueError(f"Local upload file not found: {local_path}")
        return str(local_path)

    return normalized


def resync_admin_honor_images_to_cloudinary(db: Session, *, actor_id: int | None = None) -> dict[str, Any]:
    if settings.media_storage.strip().lower() != "cloudinary":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MEDIA_STORAGE must be set to cloudinary to run this action.",
        )
    _configure_cloudinary()

    honors = db.scalars(
        select(Honor).where(Honor.deleted_at.is_(None)).order_by(Honor.id)
    ).all()

    total = len(honors)
    updated = 0
    skipped = 0
    failed = 0
    failed_items: list[dict[str, Any]] = []
    folder = f"{settings.cloudinary_folder.strip('/')}/honors"

    for honor in honors:
        source_url = str(honor.image_url or "").strip()
        if not source_url:
            skipped += 1
            continue
        if source_url.startswith(CLOUDINARY_URL_PREFIX):
            skipped += 1
            continue

        try:
            upload_source = _resolve_upload_source(source_url)
            public_id = honor.slug or f"honor-{honor.id}"
            result = cloudinary.uploader.upload(
                upload_source,
                folder=folder,
                public_id=public_id,
                overwrite=True,
                resource_type="image",
            )
            secure_url = str(result.get("secure_url") or result.get("url") or "").strip()
            if not secure_url:
                raise ValueError("Cloudinary response missing secure_url.")

            honor.image_url = secure_url
            honor.updated_by = actor_id
            db.add(honor)
            updated += 1
        except Exception as exc:
            failed += 1
            failed_items.append(
                {
                    "id": honor.id,
                    "title": honor.title,
                    "source_url": source_url,
                    "reason": str(exc),
                }
            )

    db.commit()
    return {
        "total": total,
        "updated": updated,
        "skipped": skipped,
        "failed": failed,
        "failed_items": failed_items[:20],
    }


def list_public_honors(db: Session, *, year: int | None = None) -> dict[str, Any]:
    query = (
        select(Honor)
        .options(selectinload(Honor.category))
        .where(Honor.deleted_at.is_(None), Honor.is_active.is_(True))
        .order_by(Honor.sort_order, Honor.year.desc().nullslast(), Honor.id.desc())
    )
    if year:
        query = query.where(Honor.year == year)

    records = db.scalars(query).all()
    grouped: dict[str, list[dict[str, Any]]] = {
        "qualification_certificates": [],
        "corporate_honors": [],
        "project_honors": [],
    }
    all_items: list[dict[str, Any]] = []

    for record in records:
        if record.category and (record.category.deleted_at is not None or not record.category.is_active):
            continue

        item = _honor_payload(record)
        all_items.append(item)

        if record.display_type == "corporate_honors":
            grouped["corporate_honors"].append(item)
        elif record.display_type == "project_honors":
            grouped["project_honors"].append(item)
        else:
            grouped["qualification_certificates"].append(item)

    return {
        "hero": {
            "title": "QUALIFICATION HONOR",
            "description": "Make customers satisfied, make employees proud, let the world recognize",
            "background": "https://en.sinodecor.com/portal-local/ngc202304190002/cms/image/ee391405-cb7a-4434-91fa-fcf427544b97.jpg",
            "mobile_background": "https://en.sinodecor.com/repository/portal-local/ngc202304190002/cms/image/478d7a9b-32d8-4f48-a644-7790d0ebbe19.jpeg",
            "accent": "https://omo-oss-image.thefastimg.com/portal-saas/ngc202303290005/cms/image/53e45437-3eaa-453a-87e7-5d86b6f29064.png",
        },
        "sections": grouped,
        "items": all_items,
    }
