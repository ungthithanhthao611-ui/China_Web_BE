from concurrent.futures import ThreadPoolExecutor
from typing import Any

from fastapi import HTTPException, status
from pydantic import ValidationError
from sqlalchemy import asc, delete, desc, func, inspect, or_, select, String, cast
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload, joinedload

from app.core.config import settings
from app.core.security import hash_password
from app.models.content import Banner, ContentBlock, ContentBlockItem, Page, PageSection
from app.models.media import EntityMedia, MediaAsset
from app.models.orders import Order
from app.models.organization import Video
from app.models.products import Product, ProductCategory, ProductImage
from app.models.projects import Project, ProjectCategory, ProjectCategoryItem, ProjectProduct
from app.models.taxonomy import Language
from app.models.user import User, UserLoginHistory
from app.schemas.user import UserLoginHistoryRead
from app.services.media import delete_media_asset_record
from app.services.catalog import ENTITY_REGISTRY, EntityRegistration
from app.services.orders import (
    _payment_method_label,
    _payment_status_label,
    _status_label,
)
from app.services.product_pricing import (
    decorate_product_pricing_payload,
    normalize_product_pricing_input,
)
from app.services.public import invalidate_public_cache
from app.utils.contact_maps import normalize_contact_payload
from app.services.translator import smart_translate

try:
    from app.services.wordpress_sync import delete_wordpress_post
except ModuleNotFoundError:
    delete_wordpress_post = None


def get_registration(entity_name: str) -> EntityRegistration:
    registration = ENTITY_REGISTRY.get(entity_name)
    if not registration:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Entity '{entity_name}' is not registered.",
        )
    return registration


PUBLIC_CACHE_ENTITY_NAMES = {
    "banners",
    "content_blocks",
    "content_block_items",
    "media_assets",
    "page_sections",
    "pages",
    "site_settings",
}


def _entity_affects_public_cache(entity_name: str) -> bool:
    return str(entity_name or "").strip().lower() in PUBLIC_CACHE_ENTITY_NAMES


def _clean_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _about_section_from_block_key(block_key: Any) -> str:
    mapping = {
        "hero_summary": "hero",
        "intro_media": "company_introduction",
        "intro_video": "company_introduction",
        "intro_paragraphs": "company_introduction",
        "speech_profile": "chairman_speech",
        "speech_body": "chairman_speech",
        "speech_signature": "chairman_speech",
        "org_chart_image": "organization_chart",
        "culture_purpose": "corporate_culture",
        "culture_mission": "corporate_culture",
        "culture_spirit": "corporate_culture",
        "culture_values": "corporate_culture",
        "culture_slogan": "corporate_culture",
        "timeline": "development_course",
        "leadership_care_gallery": "leadership_care",
    }
    return mapping.get(_clean_text(block_key), "")


def _is_empty_text(value: Any) -> bool:
    return not str(value or "").strip()


def _serialize_media(record: MediaAsset | None) -> dict[str, Any] | None:
    if not record:
        return None

    registration = get_registration("media_assets")
    return registration.read_schema.model_validate(record).model_dump(mode="json")


def _stringify_project_case_ids(entity_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    fields_to_stringify: tuple[str, ...] = ()

    if entity_name == "project_categories":
        fields_to_stringify = ("id", "parent_id")
    elif entity_name == "product_categories":
        fields_to_stringify = ("id", "parent_id")
    elif entity_name == "projects":
        fields_to_stringify = ("category_id",)
    elif entity_name == "project_category_items":
        fields_to_stringify = ("category_id",)
    elif entity_name == "project_products":
        fields_to_stringify = ("project_id", "product_id")
    elif entity_name == "entity_media" and str(payload.get("entity_type") or "").strip() in {
        "project_category",
        "project_categories",
    }:
        fields_to_stringify = ("entity_id",)

    for field_name in fields_to_stringify:
        value = payload.get(field_name)
        if value is None or value == "":
            continue
        payload[field_name] = str(value)

    return payload


def _decorate_project_case_admin_payload(
    db: Session,
    entity_name: str,
    record: Any,
    payload: dict[str, Any],
) -> dict[str, Any]:
    if entity_name == "page_sections":
        page = db.get(Page, getattr(record, "page_id", None)) if getattr(record, "page_id", None) else None
        if page:
            payload["page_label"] = page.title or page.slug
            payload["page_slug"] = page.slug

            about_route_map = {
                "hero": "/about/company-introduction#page1",
                "company_introduction": "/about/company-introduction#page2",
                "chairman_speech": "/about/chairman-speech#page3",
                "organization_chart": "/about/organization-chart#page4",
                "corporate_culture": "/about/corporate-culture#page5",
                "development_course": "/about/development-course#page6",
                "leadership_care": "/about/leadership-care#page7",
            }
            anchor = str(payload.get("anchor") or getattr(record, "anchor", "")).strip().lower()
            if page.slug == "about":
                payload["preview_href"] = about_route_map.get(anchor, "/about/company-introduction#page1")
        return payload

    if entity_name != "entity_media":
        return payload

    entity_type = str(payload.get("entity_type") or getattr(record, "entity_type", "")).strip()
    entity_id = getattr(record, "entity_id", None)
    if entity_id is None:
        return payload

    if entity_type in {"project_category", "project_categories"}:
        category = db.get(ProjectCategory, entity_id)
        if category:
            payload["entity_label"] = category.name
            payload["preview_href"] = f"/project_list/{category.id}.html"
        return payload

    if entity_type == "project":
        project = db.get(Project, entity_id)
        if project:
            payload["entity_label"] = project.title
            payload["entity_slug"] = project.slug
            payload["preview_href"] = f"/project/{project.slug}"
        return payload

    return payload



def _base_query_for_model(model: type):
    query = select(model)

    if model is Banner:
        return query.options(selectinload(Banner.image))

    if model is ContentBlockItem:
        return query.options(
            selectinload(ContentBlockItem.block),
            selectinload(ContentBlockItem.image),
        )

    if model is Video:
        return query.options(
            selectinload(Video.thumbnail),
            selectinload(Video.product),
        )

    if model is Product:
        return query.options(selectinload(Product.images), selectinload(Product.category))

    if model is ProductCategory:
        return query.options(selectinload(ProductCategory.parent))

    if model is ProjectProduct:
        return query.options(
            selectinload(ProjectProduct.project),
            selectinload(ProjectProduct.product),
        )

    if model is Order:
        return query.options(selectinload(Order.items))

    if model is User:
        return query.options(selectinload(User.login_history))

    return query




def serialize(db: Session, record: Any, registration: EntityRegistration) -> dict[str, Any]:
    payload = registration.read_schema.model_validate(record).model_dump(mode="json")

    if isinstance(record, Banner):
        payload["image"] = _serialize_media(getattr(record, "image", None))

    if isinstance(record, ContentBlockItem):
        block = getattr(record, "block", None)
        image = getattr(record, "image", None)
        payload["image"] = _serialize_media(image)
        payload["image_url"] = getattr(image, "url", None) if image else None
        payload["block_key"] = getattr(block, "block_key", None) if block else None
        payload["block_title"] = getattr(block, "title", None) if block else None
        payload["block_type"] = getattr(block, "block_type", None) if block else None
        payload["section_key"] = _about_section_from_block_key(payload.get("block_key"))

    if isinstance(record, Video):
        payload["product_name"] = record.product.name if getattr(record, "product", None) else None
        payload["thumbnail"] = _serialize_media(getattr(record, "thumbnail", None))

    if isinstance(record, Product):
        payload["gallery_urls"] = "\n".join(
            [img.url for img in sorted(getattr(record, "images", []) or [], key=lambda item: (item.sort_order, item.id))]
        )
        payload["category_name"] = record.category.name if getattr(record, "category", None) else None
        payload = decorate_product_pricing_payload(payload, record)

    if isinstance(record, ProductCategory):
        payload["parent_name"] = record.parent.name if getattr(record, "parent", None) else None

    if isinstance(record, ProjectProduct):
        payload["project_name"] = record.project.title if getattr(record, "project", None) else None
        payload["product_name"] = record.product.name if getattr(record, "product", None) else None

    if isinstance(record, Order):
        payload["status_label"] = _status_label(getattr(record, "status", None))
        payload["payment_method_label"] = _payment_method_label(getattr(record, "payment_method", None))
        payload["payment_status_label"] = _payment_status_label(getattr(record, "payment_status", None))
        payload["item_count"] = sum(int(getattr(item, "quantity", 0) or 0) for item in (getattr(record, "items", []) or []))

    if isinstance(record, User):
        history_records = sorted(
            list(getattr(record, "login_history", []) or []),
            key=lambda item: (
                getattr(item, "login_at", None) or getattr(item, "created_at", None),
                getattr(item, "id", 0),
            ),
            reverse=True,
        )
        payload["login_history"] = [
            UserLoginHistoryRead.model_validate(item, from_attributes=True).model_dump(mode="json")
            for item in history_records
        ]
        payload["login_history_count"] = len(history_records)

    payload = _stringify_project_case_ids(registration.model.__tablename__, payload)
    return _decorate_project_case_admin_payload(db, registration.model.__tablename__, record, payload)


def _sync_product_images(db: Session, product: Product, gallery_urls: str | None) -> None:
    del db

    raw_gallery_urls = str(gallery_urls or "")
    primary_url = str(getattr(product, "image_url", "") or "").strip()
    urls = [
        line.strip()
        for line in raw_gallery_urls.replace("\r", "\n").split("\n")
        if line.strip()
    ]

    deduplicated_urls: list[str] = []
    seen: set[str] = set()
    for url in urls:
        if url == primary_url or url in seen:
            continue
        seen.add(url)
        deduplicated_urls.append(url)

    product.images.clear()
    for index, url in enumerate(deduplicated_urls):
        product.images.append(ProductImage(url=url, alt=product.name, sort_order=index))



def _normalize_validation_errors(exc: ValidationError) -> list[dict[str, Any]]:
    normalized_errors: list[dict[str, Any]] = []
    for error in exc.errors():
        normalized_error = dict(error)
        ctx = normalized_error.get("ctx")
        if isinstance(ctx, dict):
            normalized_error["ctx"] = {
                key: str(value) if isinstance(value, Exception) else value
                for key, value in ctx.items()
            }
        normalized_errors.append(normalized_error)
    return normalized_errors


def get_admin_entity_names() -> list[str]:
    return sorted(ENTITY_REGISTRY.keys())


def _format_record_label(record: Any, fallback: str = "record") -> str:
    for field_name in ("title", "name", "slug"):
        value = getattr(record, field_name, None)
        if value:
            return str(value).strip()
    return fallback


def _raise_delete_dependency_error(db: Session, entity_name: str, record: Any) -> None:
    if entity_name == "project_categories":
        projects_count = db.scalar(select(func.count()).select_from(Project).where(Project.category_id == record.id)) or 0
        child_count = db.scalar(select(func.count()).select_from(ProjectCategory).where(ProjectCategory.parent_id == record.id)) or 0
        linked_count = (
            db.scalar(
                select(func.count())
                .select_from(ProjectCategoryItem)
                .where(ProjectCategoryItem.category_id == record.id)
            )
            or 0
        )

        reasons: list[str] = []
        if projects_count:
            reasons.append(f"it is assigned to {projects_count} project{'s' if projects_count != 1 else ''}")
        if child_count:
            reasons.append(f"it has {child_count} child categor{'ies' if child_count != 1 else 'y'}")
        if linked_count:
            reasons.append(
                f"it is linked in {linked_count} project-case mapping record{'s' if linked_count != 1 else ''}"
            )

        if reasons:
            label = _format_record_label(record, fallback="this category")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f'Cannot delete Project Category "{label}" because ' + " and ".join(reasons) + ".",
            )


def _raise_friendly_delete_integrity_error(entity_name: str, record: Any) -> None:
    label = _format_record_label(record)
    entity_label = entity_name.replace("_", " ").rstrip("s") or "record"
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=f'Cannot delete {entity_label} "{label}" because it is still referenced by other records.',
    )


def _raise_friendly_write_integrity_error(entity_name: str) -> None:
    if entity_name == "project_category_items":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Project case mapping must use a unique project and a unique anchor within the same category."
            ),
        )

    if entity_name == "project_products":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project -> Product mapping must be unique. A product cannot be linked twice to the same project.",
        )

    entity_label = entity_name.replace("_", " ").rstrip("s") or "record"
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=f"Cannot save {entity_label} because a unique field conflicts with an existing record.",
    )


def _validate_product_category_parent(
    db: Session,
    *,
    parent_id: int | None,
    current_category_id: int | None = None,
) -> int | None:
    if parent_id is None:
        return None

    parent = db.get(ProductCategory, parent_id)
    if not parent:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Parent product category does not exist.",
        )

    # Parent options must be top-level categories.
    if parent.parent_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Invalid parent category: only top-level categories can be selected as parent.",
        )

    if current_category_id is not None and parent_id == current_category_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A product category cannot be its own parent.",
        )

    # Prevent cycles: current category cannot appear in the parent chain.
    if current_category_id is not None:
        seen: set[int] = set()
        cursor: ProductCategory | None = parent
        while cursor is not None:
            if cursor.id == current_category_id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Invalid parent category: this assignment creates a cyclic hierarchy.",
                )
            if cursor.id in seen:
                break
            seen.add(cursor.id)
            cursor = db.get(ProductCategory, cursor.parent_id) if cursor.parent_id else None

    return parent_id


def _validate_video_product_id(db: Session, *, product_id: int | None) -> int | None:
    if product_id is None:
        return None

    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Selected product does not exist.",
        )

    return product_id


def _apply_admin_pages_filter(entity_name: str, model: type, query, count_query):
    if entity_name == "pages" and model is Page:
        canonical_about_condition = func.lower(func.coalesce(model.slug, "")) == "about"
        return query.where(canonical_about_condition), count_query.where(canonical_about_condition)

    if entity_name == "page_sections" and model is PageSection:
        about_page_ids = select(Page.id).where(func.lower(func.coalesce(Page.slug, "")) == "about")
        about_sections_condition = model.page_id.in_(about_page_ids)
        return query.where(about_sections_condition), count_query.where(about_sections_condition)

    if entity_name == "content_blocks" and model is ContentBlock:
        about_page_ids = select(Page.id).where(func.lower(func.coalesce(Page.slug, "")) == "about")
        about_blocks_condition = (
            (func.lower(func.coalesce(model.entity_type, "")) == "page")
            & model.entity_id.in_(about_page_ids)
        )
        return query.where(about_blocks_condition), count_query.where(about_blocks_condition)

    return query, count_query



def list_entity_records(
    db: Session,
    entity_name: str,
    skip: int,
    limit: int,
    language_id: int | None,
    status_value: str | None,
    is_active: bool | None,
    search: str | None,
    section_key: str | None = None,
    block_key: str | None = None,
    completeness: str | None = None,
    media_state: str | None = None,
    stock_state: str | None = None,
) -> dict[str, Any]:
    registration = get_registration(entity_name)
    model = registration.model
    query = _base_query_for_model(model)
    count_query = select(func.count()).select_from(model)

    if entity_name == "content_block_items":
        query = query.join(ContentBlock, ContentBlock.id == ContentBlockItem.block_id)
        count_query = count_query.select_from(ContentBlockItem).join(
            ContentBlock, ContentBlock.id == ContentBlockItem.block_id
        )

    if hasattr(model, "deleted_at"):
        deleted_at = getattr(model, "deleted_at")
        query = query.where(deleted_at.is_(None))
        count_query = count_query.where(deleted_at.is_(None))

    query, count_query = _apply_admin_pages_filter(entity_name, model, query, count_query)

    for candidate, value in {
        "language_id": language_id,
        "status": status_value,
        "is_active": is_active,
    }.items():
        if value is not None and hasattr(model, candidate):
            if candidate == "language_id" and model is Banner:
                continue

            column = getattr(model, candidate)
            query = query.where(column == value)
            count_query = count_query.where(column == value)

    if search:
        if entity_name == "content_block_items":
            search_term = f"%{search}%"
            conditions = [
                cast(ContentBlockItem.title, String).ilike(search_term),
                cast(ContentBlockItem.subtitle, String).ilike(search_term),
                cast(ContentBlockItem.content, String).ilike(search_term),
                cast(ContentBlockItem.item_key, String).ilike(search_term),
                cast(ContentBlockItem.link, String).ilike(search_term),
                cast(ContentBlock.block_key, String).ilike(search_term),
                cast(ContentBlock.title, String).ilike(search_term),
                cast(ContentBlock.subtitle, String).ilike(search_term),
            ]
            query = query.where(or_(*conditions))
            count_query = count_query.where(or_(*conditions))
        else:
            search_columns = [
                getattr(model, field_name)
                for field_name in ("title", "name", "slug", "config_key", "email")
                if hasattr(model, field_name)
            ]
            if search_columns:
                conditions = [cast(column, String).ilike(f"%{search}%") for column in search_columns]
                query = query.where(or_(*conditions))
                count_query = count_query.where(or_(*conditions))

    normalized_stock_state = _clean_text(stock_state)
    if entity_name == "products" and normalized_stock_state and hasattr(model, "stock_quantity"):
        stock_column = getattr(model, "stock_quantity")
        if normalized_stock_state == "in_stock":
            stock_condition = stock_column > 0
        elif normalized_stock_state == "low_stock":
            stock_condition = stock_column.between(1, 5)
        elif normalized_stock_state == "out_of_stock":
            stock_condition = stock_column <= 0
        else:
            stock_condition = None

        if stock_condition is not None:
            query = query.where(stock_condition)
            count_query = count_query.where(stock_condition)

    if entity_name == "content_block_items":
        normalized_block_key = _clean_text(block_key)
        normalized_section_key = _clean_text(section_key)
        normalized_completeness = _clean_text(completeness)
        normalized_media_state = _clean_text(media_state)

        about_page_ids = select(Page.id).where(func.lower(func.coalesce(Page.slug, "")) == "about")
        about_items_condition = (
            (func.lower(func.coalesce(ContentBlock.entity_type, "")) == "page")
            & ContentBlock.entity_id.in_(about_page_ids)
        )
        query = query.where(about_items_condition)
        count_query = count_query.where(about_items_condition)

        if normalized_block_key:
            block_condition = func.lower(func.coalesce(ContentBlock.block_key, "")) == normalized_block_key
            query = query.where(block_condition)
            count_query = count_query.where(block_condition)

        if normalized_section_key:
            section_to_blocks = {
                "hero": ["hero_summary"],
                "company_introduction": ["intro_media", "intro_video", "intro_paragraphs"],
                "chairman_speech": ["speech_profile", "speech_body", "speech_signature"],
                "organization_chart": ["org_chart_image"],
                "corporate_culture": [
                    "culture_purpose",
                    "culture_mission",
                    "culture_spirit",
                    "culture_values",
                    "culture_slogan",
                ],
                "development_course": ["timeline"],
                "leadership_care": ["leadership_care_gallery"],
            }
            allowed_blocks = section_to_blocks.get(normalized_section_key, [])
            if allowed_blocks:
                section_condition = func.lower(func.coalesce(ContentBlock.block_key, "")).in_(allowed_blocks)
            else:
                section_condition = func.lower(func.coalesce(ContentBlock.block_key, "")) == "__no_match__"
            query = query.where(section_condition)
            count_query = count_query.where(section_condition)

        text_present_expr = or_(
            func.length(func.trim(func.coalesce(ContentBlockItem.title, ""))) > 0,
            func.length(func.trim(func.coalesce(ContentBlockItem.subtitle, ""))) > 0,
            func.length(func.trim(func.coalesce(ContentBlockItem.content, ""))) > 0,
        )
        image_present_expr = ContentBlockItem.image_id.is_not(None)
        link_present_expr = func.length(func.trim(func.coalesce(ContentBlockItem.link, ""))) > 0

        if normalized_completeness == "missing_content":
            query = query.where(~text_present_expr)
            count_query = count_query.where(~text_present_expr)
        elif normalized_completeness == "missing_image":
            query = query.where(~image_present_expr)
            count_query = count_query.where(~image_present_expr)
        elif normalized_completeness == "missing_link":
            query = query.where(~link_present_expr)
            count_query = count_query.where(~link_present_expr)
        elif normalized_completeness == "complete":
            query = query.where(text_present_expr, image_present_expr)
            count_query = count_query.where(text_present_expr, image_present_expr)

        if normalized_media_state == "with_media":
            query = query.where(image_present_expr)
            count_query = count_query.where(image_present_expr)
        elif normalized_media_state == "without_media":
            query = query.where(~image_present_expr)
            count_query = count_query.where(~image_present_expr)

    if hasattr(model, "sort_order"):
        query = query.order_by(getattr(model, "sort_order"), getattr(model, "id"))
    else:
        query = query.order_by(getattr(model, "id").desc())

    total = db.scalar(count_query) or 0
    records = db.scalars(query.offset(skip).limit(limit)).all()
    return {
        "items": [serialize(db, record, registration) for record in records],
        "pagination": {"skip": skip, "limit": limit, "total": total},
    }


def create_entity_record(db: Session, entity_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    registration = get_registration(entity_name)
    normalized_payload = normalize_contact_payload(payload) if entity_name == "contacts" else payload
    try:
        data = registration.create_schema.model_validate(normalized_payload).model_dump(exclude_none=True)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=_normalize_validation_errors(exc),
        ) from exc
    product_gallery_urls = None
    if entity_name == "products":
        data = normalize_product_pricing_input(data)
        product_gallery_urls = data.pop("gallery_urls", None)
    if entity_name == "users":
        raw_password = str(data.pop("password", "")).strip()
        if not raw_password:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Password is required when creating a user.",
            )
        data["password_hash"] = hash_password(raw_password)
    if entity_name == "product_categories":
        data["parent_id"] = _validate_product_category_parent(
            db,
            parent_id=data.get("parent_id"),
        )
    if entity_name == "videos":
        data["product_id"] = _validate_video_product_id(
            db,
            product_id=data.get("product_id"),
        )

    record = registration.model(**data)
    db.add(record)
    try:
        db.commit()
        if entity_name == "products" and product_gallery_urls is not None:
            _sync_product_images(db, record, product_gallery_urls)
            db.add(record)
            db.commit()
    except IntegrityError:
        db.rollback()
        _raise_friendly_write_integrity_error(entity_name)

    if _entity_affects_public_cache(entity_name):
        invalidate_public_cache()

    return get_entity_record(db=db, entity_name=entity_name, record_id=record.id)


def get_entity_record(db: Session, entity_name: str, record_id: int) -> dict[str, Any]:
    registration = get_registration(entity_name)
    record = db.scalar(_base_query_for_model(registration.model).where(registration.model.id == record_id))
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Record not found.")
    return serialize(db, record, registration)


def update_entity_record(db: Session, entity_name: str, record_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    registration = get_registration(entity_name)
    record = db.get(registration.model, record_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Record not found.")

    # Keep explicit null values from admin forms so users can clear optional fields.
    normalized_payload = normalize_contact_payload(payload) if entity_name == "contacts" else payload
    try:
        data = registration.update_schema.model_validate(normalized_payload).model_dump(exclude_unset=True)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=_normalize_validation_errors(exc),
        ) from exc
    product_gallery_urls = None
    if entity_name == "products":
        data = normalize_product_pricing_input(data)
        product_gallery_urls = data.pop("gallery_urls", None)
    if entity_name == "users":
        raw_password = data.pop("password", None)
        if raw_password is not None:
            normalized_password = str(raw_password).strip()
            if not normalized_password:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Password cannot be empty.",
                )
            data["password_hash"] = hash_password(normalized_password)
    if entity_name == "product_categories" and "parent_id" in data:
        data["parent_id"] = _validate_product_category_parent(
            db,
            parent_id=data.get("parent_id"),
            current_category_id=record_id,
        )
    if entity_name == "videos" and "product_id" in data:
        data["product_id"] = _validate_video_product_id(
            db,
            product_id=data.get("product_id"),
        )

    for field_name, value in data.items():
        setattr(record, field_name, value)

    if entity_name == "products" and product_gallery_urls is not None:
        _sync_product_images(db, record, product_gallery_urls)

    db.add(record)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        _raise_friendly_write_integrity_error(entity_name)

    if _entity_affects_public_cache(entity_name):
        invalidate_public_cache()

    return get_entity_record(db=db, entity_name=entity_name, record_id=record_id)


def delete_entity_record(db: Session, entity_name: str, record_id: int) -> None:
    registration = get_registration(entity_name)
    record = db.get(registration.model, record_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Record not found.")

    if entity_name == "media_assets":
        delete_media_asset_record(db=db, record=record)
        return

    if entity_name == "posts" and settings.wp_bidirectional_delete_enabled:
        post_record = record
        is_wp_managed = (
            str(post_record.source_system or "").strip().lower() == "wordpress"
            or post_record.wp_post_id is not None
        )
        if is_wp_managed and delete_wordpress_post:
            delete_wordpress_post(
                wp_post_id=post_record.wp_post_id,
                slug=post_record.slug,
            )

    _raise_delete_dependency_error(db=db, entity_name=entity_name, record=record)

    try:
        db.delete(record)
        db.commit()
    except IntegrityError:
        db.rollback()
        _raise_friendly_delete_integrity_error(entity_name=entity_name, record=record)

    if _entity_affects_public_cache(entity_name):
        invalidate_public_cache()


def _language_by_code(db: Session, code: str) -> Language | None:
    return db.scalar(
        select(Language).where(
            func.lower(Language.code) == str(code or "").strip().lower(),
            Language.status == "active",
        )
    )


def _unique_project_slug(db: Session, base_slug: str, language_code: str, current_project_id: int | None = None) -> str:
    normalized_base = str(base_slug or "project").strip().strip("-") or "project"
    normalized_code = str(language_code or "").strip().lower()
    seed_slug = f"{normalized_base}-{normalized_code}" if normalized_code else normalized_base
    candidate = seed_slug
    index = 2

    while True:
        query = select(Project.id).where(Project.slug == candidate)
        existing_id = db.scalar(query)
        if existing_id is None or (current_project_id is not None and int(existing_id) == int(current_project_id)):
            return candidate
        candidate = f"{seed_slug}-{index}"
        index += 1


def _copy_project_relations_for_translation(db: Session, source: Project, target: Project) -> None:
    existing_product_ids = {
        int(item.product_id)
        for item in db.scalars(select(ProjectProduct).where(ProjectProduct.project_id == target.id)).all()
    }
    source_products = db.scalars(
        select(ProjectProduct).where(ProjectProduct.project_id == source.id).order_by(ProjectProduct.sort_order, ProjectProduct.id)
    ).all()
    for item in source_products:
        if int(item.product_id) in existing_product_ids:
            continue
        db.add(
            ProjectProduct(
                project_id=target.id,
                product_id=item.product_id,
                sort_order=item.sort_order,
                note=item.note,
            )
        )

    existing_media_keys = {
        (int(item.media_id), str(item.group_name or "default"))
        for item in db.scalars(
            select(EntityMedia).where(
                EntityMedia.entity_type == "project",
                EntityMedia.entity_id == target.id,
            )
        ).all()
    }
    source_media = db.scalars(
        select(EntityMedia)
        .where(EntityMedia.entity_type == "project", EntityMedia.entity_id == source.id)
        .order_by(EntityMedia.group_name, EntityMedia.sort_order, EntityMedia.id)
    ).all()
    for item in source_media:
        key = (int(item.media_id), str(item.group_name or "default"))
        if key in existing_media_keys:
            continue
        db.add(
            EntityMedia(
                entity_type="project",
                entity_id=target.id,
                media_id=item.media_id,
                group_name=item.group_name,
                sort_order=item.sort_order,
                caption=item.caption,
            )
        )


def _translated_project_payload(source: Project, target_language_code: str) -> dict[str, Any]:
    translated_fields: dict[str, Any] = {}
    for field_name in ("title", "summary", "body", "location", "meta_title", "meta_description"):
        value = getattr(source, field_name, None)
        translated_fields[field_name] = (
            smart_translate(value, target_language_code)
            if isinstance(value, str) and value.strip()
            else value
        )

    return {
        "category_id": source.category_id,
        "summary": translated_fields.get("summary"),
        "body": translated_fields.get("body"),
        "location": translated_fields.get("location"),
        "project_year": source.project_year,
        "image_id": source.image_id,
        "hero_image_id": source.hero_image_id,
        "status": "draft",
        "meta_title": translated_fields.get("meta_title"),
        "meta_description": translated_fields.get("meta_description"),
        "legacy_detail_id": source.legacy_detail_id,
        "legacy_detail_href": source.legacy_detail_href,
        "title": translated_fields.get("title") or source.title,
    }


def _auto_translate_project_record(db: Session, record: Project) -> dict[str, Any]:
    translated_project_ids: list[int] = []

    for language_code in ("en", "zh"):
        language = _language_by_code(db, language_code)
        if not language:
            continue

        preferred_slug = f"{str(record.slug or 'project').strip().strip('-')}-{language_code}"
        target = db.scalar(
            select(Project).where(
                Project.slug == preferred_slug,
                Project.language_id == language.id,
            )
        )

        translated_payload = _translated_project_payload(record, language_code)
        if target is None:
            target_slug = _unique_project_slug(db, record.slug, language_code)
            target = Project(
                **translated_payload,
                slug=target_slug,
                language_id=language.id,
            )
            db.add(target)
            db.flush()
        else:
            for field_name, value in translated_payload.items():
                current_value = getattr(target, field_name, None)
                if current_value is None or (isinstance(current_value, str) and not current_value.strip()):
                    setattr(target, field_name, value)

        _copy_project_relations_for_translation(db=db, source=record, target=target)
        translated_project_ids.append(target.id)

    db.commit()
    return {
        "source": get_entity_record(db=db, entity_name="projects", record_id=record.id),
        "translations": [
            get_entity_record(db=db, entity_name="projects", record_id=project_id)
            for project_id in translated_project_ids
        ],
    }


# Map of entity_name -> source fields that should be auto-translated.
# Centralized so both record-level and payload-level translation share it.
TRANSLATABLE_FIELDS_MAP: dict[str, list[str]] = {
    "products": ["name", "short_desc", "full_desc", "size", "material", "color", "use_case"],
    "product_categories": ["name", "description"],
    "projects": ["title", "summary", "body", "location", "meta_title", "meta_description"],
    "news_posts": ["title", "summary", "content", "meta_title", "meta_description"],
    "content_block_items": ["title", "subtitle", "content"],
}
TRANSLATION_TARGET_LANGS: tuple[str, ...] = ("en", "zh")


def _build_translation_jobs(
    fields: list[str],
    source_lookup,
    *,
    skip_if_filled,
) -> list[tuple[str, str, str]]:
    """
    Build (field, lang, source_text) jobs for parallel translation.

    `source_lookup(field)` returns the source text (or None).
    `skip_if_filled(field, lang)` returns True if target already has data
    so we shouldn't overwrite.
    """
    jobs: list[tuple[str, str, str]] = []
    for field in fields:
        source_val = source_lookup(field)
        if not source_val or not isinstance(source_val, str):
            continue
        for lang in TRANSLATION_TARGET_LANGS:
            if skip_if_filled(field, lang):
                continue
            jobs.append((field, lang, source_val))
    return jobs


def _run_translation_jobs(
    jobs: list[tuple[str, str, str]],
) -> list[tuple[str, str, str]]:
    """
    Execute translation jobs in parallel and return
    a list of (field, lang, translated_text).
    Empty job list -> empty result, no thread pool created.
    """
    if not jobs:
        return []

    # Cap workers to avoid hammering Google with too many sockets at once.
    max_workers = min(8, len(jobs))
    results: list[tuple[str, str, str]] = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_map = {
            pool.submit(smart_translate, source_val, lang): (field, lang)
            for field, lang, source_val in jobs
        }
        for future in future_map:
            field, lang = future_map[future]
            try:
                translated = future.result(timeout=20)
            except Exception:  # noqa: BLE001
                # smart_translate already swallows errors, but guard the
                # future itself (eg. timeout) to keep the batch alive.
                translated = ""
            results.append((field, lang, translated))
    return results


def auto_translate_record(db: Session, entity_name: str, record_id: int) -> dict[str, Any]:
    if entity_name not in TRANSLATABLE_FIELDS_MAP:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Auto-translation is not supported for entity '{entity_name}'.",
        )

    registration = get_registration(entity_name)
    record = db.get(registration.model, record_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Record not found.")

    fields = TRANSLATABLE_FIELDS_MAP[entity_name]

    def _source_lookup(field: str):
        return getattr(record, field, None)

    def _skip_if_filled(field: str, lang: str) -> bool:
        target_attr = f"{field}_{lang}"
        if not hasattr(record, target_attr):
            return True
        current = getattr(record, target_attr, None)
        return bool(current and str(current).strip())

    jobs = _build_translation_jobs(fields, _source_lookup, skip_if_filled=_skip_if_filled)
    for field, lang, translated in _run_translation_jobs(jobs):
        target_attr = f"{field}_{lang}"
        if translated and hasattr(record, target_attr):
            setattr(record, target_attr, translated)

    db.add(record)
    db.commit()
    return get_entity_record(db=db, entity_name=entity_name, record_id=record_id)


def auto_translate_payload(entity_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    if entity_name not in TRANSLATABLE_FIELDS_MAP:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Auto-translation is not supported for entity '{entity_name}'.",
        )

    result = dict(payload or {})
    fields = TRANSLATABLE_FIELDS_MAP[entity_name]

    def _source_lookup(field: str):
        return result.get(field)

    def _skip_if_filled(_field: str, _lang: str) -> bool:
        # Payload (preview) flow: always re-translate so the editor can see
        # the latest output. The translator itself is cached, so identical
        # texts are essentially free.
        return False

    jobs = _build_translation_jobs(fields, _source_lookup, skip_if_filled=_skip_if_filled)
    for field, lang, translated in _run_translation_jobs(jobs):
        if translated:
            result[f"{field}_{lang}"] = translated

    return result

