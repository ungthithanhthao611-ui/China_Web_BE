from typing import Any

from fastapi import HTTPException, status
from pydantic import ValidationError
from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.models.content import Banner
from app.models.media import MediaAsset
from app.models.news import Post, PostCategory
from app.models.organization import Video
from app.models.projects import Project, ProjectCategory, ProjectCategoryItem
from app.services.media import delete_media_asset_record
from app.services.catalog import ENTITY_REGISTRY, EntityRegistration
from app.services.wordpress_sync import delete_wordpress_post


def get_registration(entity_name: str) -> EntityRegistration:
    registration = ENTITY_REGISTRY.get(entity_name)
    if not registration:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Entity '{entity_name}' is not registered.",
        )
    return registration


def _serialize_media(record: MediaAsset | None) -> dict[str, Any] | None:
    if not record:
        return None

    registration = get_registration("media_assets")
    return registration.read_schema.model_validate(record).model_dump(mode="json")


def _base_query_for_model(model: type):
    query = select(model)

    if model is Banner:
        return query.options(selectinload(Banner.image))

    if model is Video:
        return query.options(selectinload(Video.thumbnail))

    return query


def serialize(record: Any, registration: EntityRegistration) -> dict[str, Any]:
    payload = registration.read_schema.model_validate(record).model_dump(mode="json")

    if isinstance(record, Banner):
        payload["image"] = _serialize_media(getattr(record, "image", None))

    if isinstance(record, Video):
        payload["thumbnail"] = _serialize_media(getattr(record, "thumbnail", None))

    return payload


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
    if entity_name == "post_categories":
        posts_query = (
            select(Post.id, Post.title, Post.slug)
            .where(Post.category_id == record.id)
            .order_by(Post.id.asc())
        )
        blocking_posts = db.execute(posts_query.limit(3)).all()
        posts_count = db.scalar(select(func.count()).select_from(Post).where(Post.category_id == record.id)) or 0
        child_count = db.scalar(select(func.count()).select_from(PostCategory).where(PostCategory.parent_id == record.id)) or 0

        reasons: list[str] = []
        if posts_count:
            reasons.append(f"it is assigned to {posts_count} post{'s' if posts_count != 1 else ''}")
        if child_count:
            reasons.append(f"it has {child_count} child categor{'ies' if child_count != 1 else 'y'}")

        if reasons:
            label = _format_record_label(record, fallback="this category")
            detail = f'Cannot delete Post Category "{label}" because ' + " and ".join(reasons) + "."

            if blocking_posts:
                blocking_post_labels = [
                    f'#{post_id} "{(title or "Untitled post").strip()}" (slug: {slug or "-"})'
                    for post_id, title, slug in blocking_posts
                ]
                detail += " Blocking posts: " + "; ".join(blocking_post_labels) + "."
                if posts_count > len(blocking_posts):
                    detail += f" And {posts_count - len(blocking_posts)} more post{'s' if posts_count - len(blocking_posts) != 1 else ''}."

            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=detail,
            )

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

    entity_label = entity_name.replace("_", " ").rstrip("s") or "record"
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=f"Cannot save {entity_label} because a unique field conflicts with an existing record.",
    )


def list_entity_records(
    db: Session,
    entity_name: str,
    skip: int,
    limit: int,
    language_id: int | None,
    status_value: str | None,
    is_active: bool | None,
    search: str | None,
) -> dict[str, Any]:
    registration = get_registration(entity_name)
    model = registration.model
    query = _base_query_for_model(model)
    count_query = select(func.count()).select_from(model)

    if hasattr(model, "deleted_at"):
        deleted_at = getattr(model, "deleted_at")
        query = query.where(deleted_at.is_(None))
        count_query = count_query.where(deleted_at.is_(None))

    for candidate, value in {
        "language_id": language_id,
        "status": status_value,
        "is_active": is_active,
    }.items():
        if value is not None and hasattr(model, candidate):
            column = getattr(model, candidate)
            query = query.where(column == value)
            count_query = count_query.where(column == value)

    if search:
        search_columns = [
            getattr(model, field_name)
            for field_name in ("title", "name", "slug", "config_key", "email")
            if hasattr(model, field_name)
        ]
        if search_columns:
            conditions = [cast(column, String).ilike(f"%{search}%") for column in search_columns]
            query = query.where(or_(*conditions))
            count_query = count_query.where(or_(*conditions))

    if hasattr(model, "sort_order"):
        query = query.order_by(getattr(model, "sort_order"), getattr(model, "id"))
    else:
        query = query.order_by(getattr(model, "id").desc())

    total = db.scalar(count_query) or 0
    records = db.scalars(query.offset(skip).limit(limit)).all()
    return {
        "items": [serialize(record, registration) for record in records],
        "pagination": {"skip": skip, "limit": limit, "total": total},
    }


def create_entity_record(db: Session, entity_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    registration = get_registration(entity_name)
    try:
        data = registration.create_schema.model_validate(payload).model_dump(exclude_none=True)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=_normalize_validation_errors(exc),
        ) from exc
    record = registration.model(**data)
    db.add(record)
    try:
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
    return serialize(record, registration)


def update_entity_record(db: Session, entity_name: str, record_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    registration = get_registration(entity_name)
    record = db.get(registration.model, record_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Record not found.")

    # Keep explicit null values from admin forms so users can clear optional fields.
    try:
        data = registration.update_schema.model_validate(payload).model_dump(exclude_unset=True)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=_normalize_validation_errors(exc),
        ) from exc
    for field_name, value in data.items():
        setattr(record, field_name, value)

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
        post_record: Post = record
        is_wp_managed = (
            str(post_record.source_system or "").strip().lower() == "wordpress"
            or post_record.wp_post_id is not None
        )
        if is_wp_managed:
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
