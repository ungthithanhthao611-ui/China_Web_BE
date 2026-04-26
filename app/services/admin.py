from typing import Any

from fastapi import HTTPException, status
from pydantic import ValidationError
from sqlalchemy import asc, delete, desc, func, inspect, or_, select, String, cast
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload, joinedload

from app.core.config import settings
from app.models.content import Banner, ContentBlock, ContentBlockItem, Page, PageSection
from app.models.media import MediaAsset
from app.models.organization import Video
from app.models.products import Product, ProductImage
from app.models.projects import Project, ProjectCategory, ProjectCategoryItem, ProjectProduct
from app.services.media import delete_media_asset_record
from app.services.catalog import ENTITY_REGISTRY, EntityRegistration
from app.utils.contact_maps import normalize_contact_payload

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
        return query.options(selectinload(Video.thumbnail))

    if model is Product:
        return query.options(selectinload(Product.images), selectinload(Product.category))

    if model is ProjectProduct:
        return query.options(
            selectinload(ProjectProduct.project),
            selectinload(ProjectProduct.product),
        )

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
        payload["thumbnail"] = _serialize_media(getattr(record, "thumbnail", None))

    if isinstance(record, Product):
        payload["gallery_urls"] = "\n".join(
            [img.url for img in sorted(getattr(record, "images", []) or [], key=lambda item: (item.sort_order, item.id))]
        )
        payload["category_name"] = record.category.name if getattr(record, "category", None) else None

    if isinstance(record, ProjectProduct):
        payload["project_name"] = record.project.title if getattr(record, "project", None) else None
        payload["product_name"] = record.product.name if getattr(record, "product", None) else None

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
                "corporate_culture": ["culture_purpose", "culture_mission", "culture_spirit", "culture_values"],
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
        product_gallery_urls = data.pop("gallery_urls", None)

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
        product_gallery_urls = data.pop("gallery_urls", None)

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
