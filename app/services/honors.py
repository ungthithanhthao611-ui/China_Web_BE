import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cloudinary
import cloudinary.uploader
from fastapi import HTTPException, status
from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.models.organization import Contact, Honor, HonorCategory
from app.models.taxonomy import SiteSetting
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
_PUBLIC_HONORS_CACHE: dict[str, dict[str, Any]] = {}
_PUBLIC_HONORS_CACHE_TTL = 120


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


def _site_settings_map(db: Session) -> dict[str, str]:
    items = db.scalars(select(SiteSetting).order_by(SiteSetting.id.asc())).all()
    payload: dict[str, str] = {}
    for item in items:
        key = str(item.config_key or "").strip()
        value = item.config_value
        if key and value not in (None, ""):
            payload[key] = value
    return payload


def _read_setting(settings_map: dict[str, str], keys: list[str], default: str = "") -> str:
    for key in keys:
        value = settings_map.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return default


def _parse_json_list(raw_value: str | None) -> list[Any]:
    if not raw_value:
        return []
    try:
        payload = json.loads(raw_value)
    except json.JSONDecodeError:
        return []
    return payload if isinstance(payload, list) else []


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_bool(value: Any, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _normalize_factory_gallery_item(item: Any, index: int) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    image_url = str(item.get("image_url") or item.get("url") or "").strip()
    if not image_url:
        return None
    return {
        "id": item.get("id") or f"factory-gallery-{index + 1}",
        "title": str(item.get("title") or "Hình ảnh nhà máy").strip(),
        "description": str(item.get("description") or item.get("short_description") or "").strip(),
        "image_url": image_url,
        "sort_order": _safe_int(item.get("sort_order"), index),
        "is_active": _as_bool(item.get("is_active"), True),
    }


def _normalize_capability_card(item: Any, index: int) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    title = str(item.get("title") or "").strip()
    description = str(item.get("description") or item.get("content") or "").strip()
    if not title and not description:
        return None
    return {
        "title": title or f"Năng lực sản xuất {index + 1}",
        "description": description,
        "icon": str(item.get("icon") or "factory").strip() or "factory",
        "sort_order": _safe_int(item.get("sort_order"), index),
        "is_active": _as_bool(item.get("is_active"), True),
    }


def _normalize_hero_banner_item(item: Any, index: int) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None

    background_image_url = str(item.get("background_image_url") or item.get("background") or "").strip()
    if not background_image_url:
        return None

    return {
        "title": str(item.get("title") or "NĂNG LỰC").strip() or "NĂNG LỰC",
        "subtitle": str(item.get("subtitle") or item.get("description") or "").strip(),
        "background_image_url": background_image_url,
        "sort_order": _safe_int(item.get("sort_order"), index),
        "is_active": _as_bool(item.get("is_active"), True),
    }


def _build_production_capabilities(settings_map: dict[str, str]) -> list[dict[str, Any]]:
    structured_items = _parse_json_list(
        _read_setting(settings_map, ["production_capabilities_json", "capability_production_cards_json"])
    )
    normalized_items = [
        item
        for index, raw_item in enumerate(structured_items)
        if (item := _normalize_capability_card(raw_item, index)) is not None and item["is_active"]
    ]
    if normalized_items:
        return sorted(normalized_items, key=lambda item: (item["sort_order"], item["title"]))

    raw_text = _read_setting(settings_map, ["factory_technology", "production_technology", "machinery_process"])
    if not raw_text:
        return []

    fallback_titles = [
        "Dây chuyền sản xuất hiện đại",
        "Máy móc tự động",
        "Kiểm soát chất lượng",
        "Năng lực cung ứng số lượng lớn",
    ]
    fallback_icons = ["factory", "cog", "shield", "boxes"]
    segments = [segment.strip(" -•\n\r\t") for segment in re.split(r"\n+|[|;]+", raw_text) if segment.strip()]

    items: list[dict[str, Any]] = []
    for index, segment in enumerate(segments[:4]):
        items.append(
            {
                "title": fallback_titles[index] if index < len(fallback_titles) else f"Năng lực {index + 1}",
                "description": segment,
                "icon": fallback_icons[index] if index < len(fallback_icons) else "factory",
                "sort_order": index,
                "is_active": True,
            }
        )
    return items


def _build_factory_stats(settings_map: dict[str, str], certificates: list[dict[str, Any]]) -> list[dict[str, str]]:
    stats_source = _parse_json_list(_read_setting(settings_map, ["factory_stats_json", "capability_factory_stats_json"]))
    structured_stats: list[dict[str, str]] = []
    for item in stats_source:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip()
        value = str(item.get("value") or "").strip()
        if label and value:
            structured_stats.append({"label": label, "value": value})
    if structured_stats:
        return structured_stats

    derived_stats = [
        {
            "label": "Diện tích nhà máy",
            "value": _read_setting(settings_map, ["factory_area", "factory_area_text", "factory_size"]),
        },
        {
            "label": "Công suất mỗi năm",
            "value": _read_setting(settings_map, ["annual_capacity", "factory_capacity", "production_capacity"]),
        },
        {
            "label": "Dây chuyền sản xuất",
            "value": _read_setting(settings_map, ["production_lines", "production_line_count", "factory_lines"]),
        },
        {
            "label": "Chứng nhận",
            "value": _read_setting(settings_map, ["factory_certifications", "factory_certificates_text"], str(len(certificates) or "")),
        },
    ]
    return [item for item in derived_stats if item["value"]]


def _select_capability_contact(db: Session) -> Contact | None:
    contacts = db.scalars(
        select(Contact)
        .where(Contact.is_primary.is_(True))
        .order_by(Contact.id.asc())
    ).all()
    if contacts:
        factory_contact = next((item for item in contacts if str(item.contact_type or "").strip().lower() == "factory"), None)
        return factory_contact or contacts[0]

    contacts = db.scalars(select(Contact).order_by(Contact.id.asc())).all()
    if not contacts:
        return None
    factory_contact = next((item for item in contacts if str(item.contact_type or "").strip().lower() == "factory"), None)
    return factory_contact or contacts[0]


def _normalize_map_embed(map_url: str | None) -> str:
    raw_value = str(map_url or "").strip()
    if not raw_value:
        return ""
    if "output=embed" in raw_value or "/maps/embed" in raw_value:
        return raw_value
    return f"https://www.google.com/maps?q={raw_value}&hl=vi&z=16&output=embed"


def _category_label(record: Honor) -> str:
    category_name = str(record.category.name).strip() if record.category and record.category.name else ""
    if category_name:
        return category_name
    if record.display_type == "corporate_honors":
        return "Corporate Honors"
    if record.display_type == "project_honors":
        return "Project Honors"
    return "Qualification Certificate"


def list_public_honors(db: Session, *, year: int | None = None) -> dict[str, Any]:
    cache_key = f"honors::{year if year is not None else '__all__'}"
    cached_payload = _PUBLIC_HONORS_CACHE.get(cache_key)
    if cached_payload is not None:
        if time.time() - cached_payload["timestamp"] < _PUBLIC_HONORS_CACHE_TTL:
            return cached_payload["data"]
        _PUBLIC_HONORS_CACHE.pop(cache_key, None)

    settings_map = _site_settings_map(db)
    contact = _select_capability_contact(db)

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
    certificates: list[dict[str, Any]] = []

    for record in records:
        if record.category and (record.category.deleted_at is not None or not record.category.is_active):
            continue

        item = _honor_payload(record)
        item["issuer"] = item.get("issued_by")
        item["description"] = item.get("short_description")
        item["category"] = _category_label(record)
        certificates.append(item)

        if record.display_type == "corporate_honors":
            grouped["corporate_honors"].append(item)
        elif record.display_type == "project_honors":
            grouped["project_honors"].append(item)
        else:
            grouped["qualification_certificates"].append(item)

    factory_gallery_raw = _parse_json_list(_read_setting(settings_map, ["factory_images_json", "capability_factory_gallery_json"]))
    factory_gallery = [
        item
        for index, raw_item in enumerate(factory_gallery_raw)
        if (item := _normalize_factory_gallery_item(raw_item, index)) is not None and item["is_active"]
    ]
    factory_gallery.sort(key=lambda item: (item["sort_order"], item["id"]))

    main_image_url = _read_setting(settings_map, ["factory_main_image_url", "capability_factory_main_image_url"])
    if not main_image_url and factory_gallery:
        main_image_url = factory_gallery[0]["image_url"]

    hero_banners_version = _read_setting(settings_map, ["capability_hero_banners_version"])

    hero_banners_raw = _parse_json_list(_read_setting(settings_map, ["capability_hero_banners_json"]))
    hero_banners = [
        {
            **item,
            "version": hero_banners_version,
        }
        for index, raw_item in enumerate(hero_banners_raw)
        if (item := _normalize_hero_banner_item(raw_item, index)) is not None and item["is_active"]
    ]
    hero_banners.sort(key=lambda item: (item["sort_order"], item["title"]))

    hero_banner_fallback = {
        "title": _read_setting(settings_map, ["capability_hero_title", "honors_hero_title"], "NĂNG LỰC"),
        "subtitle": _read_setting(
            settings_map,
            ["capability_hero_subtitle", "honors_hero_subtitle"],
            "Hình ảnh nhà máy, công nghệ sản xuất, công suất thực tế và các chứng nhận ISO, CE.",
        ),
        "background_image_url": _read_setting(
            settings_map,
            ["capability_hero_background_image_url", "honors_hero_background", "capability_hero_image_url"],
            main_image_url,
        ),
        "version": hero_banners_version,
    }
    primary_hero_banner = hero_banners[0] if hero_banners else hero_banner_fallback

    hero_banner = {
        "title": primary_hero_banner["title"],
        "subtitle": primary_hero_banner["subtitle"],
        "background_image_url": primary_hero_banner["background_image_url"],
        "version": hero_banners_version,
        "seal_text": _read_setting(settings_map, ["capability_seal_text", "honors_seal_text"], "资质"),
        "seal_image_url": _read_setting(settings_map, ["capability_seal_image_url", "honors_seal_image_url"]),
        "is_active": _as_bool(_read_setting(settings_map, ["capability_hero_is_active"], "true"), True),
    }

    factory_overview = {
        "title": _read_setting(settings_map, ["capability_factory_overview_title"], "Tổng quan nhà máy"),
        "factory_name": _read_setting(settings_map, ["factory_name", "company_name"], contact.name if contact else ""),
        "factory_address": _read_setting(settings_map, ["factory_address"], contact.address if contact else ""),
        "factory_location": _read_setting(settings_map, ["factory_location", "factory_location_text"], "Location"),
        "description": _read_setting(settings_map, ["factory_overview_description", "factory_description", "capability_factory_description"]),
        "production_technology": _read_setting(settings_map, ["factory_technology", "production_technology"]),
        "machinery_process": _read_setting(settings_map, ["machinery_process", "factory_machinery_process"]),
        "production_capacity": _read_setting(settings_map, ["factory_capacity", "production_capacity"]),
        "output_description": _read_setting(settings_map, ["factory_output_description", "output_description"]),
        "main_image_url": main_image_url,
        "stats": _build_factory_stats(settings_map, certificates),
    }

    contact_info = {
        "address": _read_setting(settings_map, ["factory_address"], contact.address if contact else ""),
        "email": contact.email if contact and contact.email else _read_setting(settings_map, ["company_email", "contact_email"]),
        "phone": contact.phone if contact and contact.phone else _read_setting(settings_map, ["company_phone", "contact_phone"]),
        "working_hours": _read_setting(settings_map, ["working_hours", "contact_working_hours"]),
        "map_embed": _normalize_map_embed(contact.map_url if contact else _read_setting(settings_map, ["company_map_url", "google_map_url"])),
        "google_map_url": contact.map_url if contact and contact.map_url else _read_setting(settings_map, ["company_map_url", "google_map_url"]),
        "contact_name": contact.name if contact else _read_setting(settings_map, ["factory_name", "company_name"]),
    }

    production_capabilities = _build_production_capabilities(settings_map)

    payload = {
        "hero_banner": hero_banner,
        "hero_banners": hero_banners,
        "capability_hero_banners_json": json.dumps(hero_banners, ensure_ascii=False),
        "factory_overview": factory_overview,
        "production_capabilities": production_capabilities,
        "factory_gallery": factory_gallery,
        "certificates": certificates,
        "contact_info": contact_info,
        "hero": {
            "title": hero_banner["title"],
            "description": hero_banner["subtitle"],
            "background": hero_banner["background_image_url"],
            "accent": hero_banner["seal_image_url"],
            "seal_text": hero_banner["seal_text"],
            "version": hero_banners_version,
            "banners_json": json.dumps(hero_banners, ensure_ascii=False),
        },
        "sections": grouped,
        "items": certificates,
    }

    _PUBLIC_HONORS_CACHE[cache_key] = {
        "data": payload,
        "timestamp": time.time(),
    }
    return payload
