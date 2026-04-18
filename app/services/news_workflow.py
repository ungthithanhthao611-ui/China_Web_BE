from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, object_session

from app.models.admin import AdminUser
from app.models.media import MediaAsset
from app.models.news import PostCategory
from app.models.news_workflow import NewsCategory, NewsPost, NewsPostVersion, SourceImportJob
from app.schemas.news_workflow import (
    NewsPostListQuery,
    NewsPostPayload,
    NewsPostUpdatePayload,
    SourceImportApplyPayload,
    SourceImportCreatePayload,
)
from app.services.media import create_uploaded_media_asset
from app.utils.html_sanitizer import sanitize_html
from app.utils.news_blocks import estimate_text_score, has_publishable_content, normalize_content_json, render_content_json_to_html
from app.utils.slug import slugify
from app.utils.source_import import fetch_source_and_parse


def _normalize_news_status(value: str | None) -> str:
    return "published" if str(value or "").strip().lower() == "published" else "draft"


def _serialize_datetime(value: datetime | None) -> str | None:
    return value.isoformat() if isinstance(value, datetime) else None


def _serialize_content_json(value: dict[str, Any] | None) -> dict[str, Any]:
    normalized = normalize_content_json(value or {})
    if not isinstance(normalized, dict):
        return {"page": {"width": 900, "background": "#ffffff"}, "blocks": []}
    return normalized


def _load_post_categories_by_slug(db: Session, slugs: set[str]) -> dict[str, PostCategory]:
    normalized = {str(slug or "").strip() for slug in slugs if str(slug or "").strip()}
    if not normalized:
        return {}
    records = db.scalars(select(PostCategory).where(PostCategory.slug.in_(normalized))).all()
    return {record.slug: record for record in records}


def _serialize_post_category_links(db: Session, workflow_categories: list[NewsCategory]) -> tuple[list[int], list[dict[str, Any]]]:
    if not workflow_categories:
        return [], []

    by_slug = _load_post_categories_by_slug(db, {item.slug for item in workflow_categories})
    category_ids: list[int] = []
    categories: list[dict[str, Any]] = []

    for item in workflow_categories:
        linked = by_slug.get(item.slug)
        if linked is not None:
            category_ids.append(int(linked.id))
            categories.append(
                {
                    "id": int(linked.id),
                    "name": linked.name,
                    "slug": linked.slug,
                }
            )
            continue

        categories.append(
            {
                "id": int(item.id),
                "name": item.name,
                "slug": item.slug,
            }
        )

    return category_ids, categories


def _serialize_post(post: NewsPost) -> dict[str, Any]:
    status = _normalize_news_status(post.status)
    session = object_session(post)
    category_ids, categories = _serialize_post_category_links(db=session, workflow_categories=list(post.categories or [])) if session else ([], [])
    return {
        "id": post.id,
        "title": post.title,
        "slug": post.slug,
        "summary": post.summary,
        "thumbnail_url": post.thumbnail_url,
        "content_json": _serialize_content_json(post.content_json),
        "content_html": post.content_html,
        "source_url": post.source_url,
        "source_note": post.source_note,
        "status": status,
        "published_at": _serialize_datetime(post.published_at) if status == "published" else None,
        "created_at": _serialize_datetime(post.created_at),
        "updated_at": _serialize_datetime(post.updated_at),
        "category_ids": category_ids,
        "categories": categories,
    }


def _serialize_version(item: NewsPostVersion) -> dict[str, Any]:
    return {
        "id": item.id,
        "post_id": item.post_id,
        "version_no": item.version_no,
        "content_json": _serialize_content_json(item.content_json),
        "content_html": item.content_html,
        "created_by": item.created_by,
        "created_at": _serialize_datetime(item.created_at),
    }


def _build_slug(db: Session, raw_slug: str | None, *, title: str, exclude_id: int | None = None) -> str:
    base_slug = slugify(raw_slug or title, fallback="news-post")
    candidate = base_slug
    suffix = 2

    while True:
        query = select(NewsPost.id).where(NewsPost.slug == candidate)
        if exclude_id is not None:
            query = query.where(NewsPost.id != exclude_id)
        found = db.scalar(query)
        if not found:
            return candidate
        candidate = f"{base_slug}-{suffix}"
        suffix += 1


def _resolve_categories(db: Session, category_ids: list[int]) -> list[NewsCategory]:
    if not category_ids:
        return []

    post_categories = db.scalars(select(PostCategory).where(PostCategory.id.in_(category_ids))).all()
    if len(post_categories) != len(set(category_ids)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="One or more category IDs are invalid.")

    records_by_slug = {item.slug: item for item in db.scalars(select(NewsCategory)).all()}
    resolved: list[NewsCategory] = []
    for post_category in post_categories:
        workflow_category = records_by_slug.get(post_category.slug)
        if workflow_category is None:
            workflow_category = NewsCategory(
                slug=post_category.slug,
                name=post_category.name,
                description=post_category.description,
            )
            db.add(workflow_category)
            db.flush()
            records_by_slug[workflow_category.slug] = workflow_category
        else:
            workflow_category.name = post_category.name
            workflow_category.description = post_category.description
            db.add(workflow_category)
        resolved.append(workflow_category)
    return resolved


def list_news_categories(db: Session) -> list[dict[str, Any]]:
    records = db.scalars(
        select(PostCategory).order_by(PostCategory.sort_order.asc(), PostCategory.id.asc())
    ).all()
    return [
        {
            "id": int(item.id),
            "name": item.name,
            "slug": item.slug,
            "description": item.description,
        }
        for item in records
    ]


def _render_and_sanitize_html(content_json: dict | None, preferred_html: str | None) -> str:
    if preferred_html and preferred_html.strip():
        return sanitize_html(preferred_html)
    generated_html = render_content_json_to_html(content_json or {})
    return sanitize_html(generated_html)


def _validate_publish_payload(post: NewsPost) -> None:
    if not str(post.title or "").strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Title is required before publishing.")
    if not str(post.slug or "").strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Slug is required before publishing.")
    if not has_publishable_content(post.content_json):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one non-empty content block is required before publishing.",
        )
    if estimate_text_score(post.content_json) < 20:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Content is too short to publish. Please provide more editorial content.",
        )


def _create_version_snapshot(db: Session, post: NewsPost, creator_id: int | None) -> None:
    latest_no = db.scalar(select(func.max(NewsPostVersion.version_no)).where(NewsPostVersion.post_id == post.id)) or 0
    snapshot = NewsPostVersion(
        post_id=post.id,
        version_no=int(latest_no) + 1,
        content_json=post.content_json,
        content_html=post.content_html,
        created_by=creator_id,
        created_at=datetime.now(timezone.utc),
    )
    db.add(snapshot)


def _get_post_or_404(db: Session, post_id: int) -> NewsPost:
    post = db.scalar(select(NewsPost).where(NewsPost.id == post_id))
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="News post not found.")
    return post


def list_admin_news(db: Session, query: NewsPostListQuery) -> dict[str, Any]:
    filters = []
    if query.keyword:
        keyword = f"%{query.keyword.strip()}%"
        filters.append(or_(NewsPost.title.ilike(keyword), NewsPost.summary.ilike(keyword)))
    if query.status:
        if query.status == "published":
            filters.append(NewsPost.status == "published")
        else:
            filters.append(NewsPost.status != "published")
    if query.category_id:
        post_category = db.scalar(select(PostCategory).where(PostCategory.id == query.category_id))
        if not post_category:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Category filter is invalid.")
        filters.append(NewsPost.categories.any(NewsCategory.slug == post_category.slug))

    base_query = select(NewsPost)
    count_query = select(func.count(NewsPost.id))
    if filters:
        base_query = base_query.where(*filters)
        count_query = count_query.where(*filters)

    total = int(db.scalar(count_query) or 0)
    offset = (query.page - 1) * query.limit
    rows = db.scalars(
        base_query.order_by(NewsPost.created_at.desc(), NewsPost.id.desc()).offset(offset).limit(query.limit)
    ).all()

    items: list[dict[str, Any]] = []
    for row in rows:
        normalized_status = _normalize_news_status(row.status)
        category_ids, categories = _serialize_post_category_links(db, list(row.categories or []))
        items.append(
            {
                "id": row.id,
                "title": row.title,
                "slug": row.slug,
                "summary": row.summary,
                "thumbnail_url": row.thumbnail_url,
                "content_json": _serialize_content_json(row.content_json),
                "status": normalized_status,
                "published_at": _serialize_datetime(row.published_at) if normalized_status == "published" else None,
                "created_at": _serialize_datetime(row.created_at),
                "updated_at": _serialize_datetime(row.updated_at),
                "category_ids": category_ids,
                "categories": categories,
            }
        )
    return {"items": items, "pagination": {"total": total, "page": query.page, "limit": query.limit}}


def get_admin_news_detail(db: Session, post_id: int) -> dict[str, Any]:
    post = _get_post_or_404(db, post_id)
    return _serialize_post(post)


def get_admin_news_versions(db: Session, post_id: int) -> list[dict[str, Any]]:
    _get_post_or_404(db, post_id)
    versions = db.scalars(
        select(NewsPostVersion)
        .where(NewsPostVersion.post_id == post_id)
        .order_by(NewsPostVersion.version_no.desc(), NewsPostVersion.id.desc())
    ).all()
    return [_serialize_version(item) for item in versions]


def create_admin_news(db: Session, payload: NewsPostPayload, actor: AdminUser) -> dict[str, Any]:
    slug = _build_slug(db, payload.slug, title=payload.title)
    normalized_json = normalize_content_json(payload.content_json.model_dump(mode="python"))
    content_html = _render_and_sanitize_html(normalized_json, payload.content_html)

    record = NewsPost(
        title=payload.title.strip(),
        slug=slug,
        summary=payload.summary,
        thumbnail_url=payload.thumbnail_url,
        content_json=normalized_json,
        content_html=content_html,
        source_url=payload.source_url,
        source_note=payload.source_note,
        status=_normalize_news_status(payload.status),
        author_id=actor.id,
        published_at=datetime.now(timezone.utc) if _normalize_news_status(payload.status) == "published" else None,
    )
    record.categories = _resolve_categories(db, payload.category_ids)

    if record.status == "published":
        _validate_publish_payload(record)

    db.add(record)
    db.commit()
    db.refresh(record)
    return _serialize_post(record)


def update_admin_news(db: Session, post_id: int, payload: NewsPostUpdatePayload, actor: AdminUser) -> dict[str, Any]:
    record = _get_post_or_404(db, post_id)
    before_json = record.content_json
    before_html = record.content_html

    update_data = payload.model_dump(exclude_unset=True)

    if "title" in update_data:
        record.title = str(update_data["title"]).strip()
    if "slug" in update_data:
        record.slug = _build_slug(db, update_data["slug"], title=record.title, exclude_id=record.id)
    if "summary" in update_data:
        record.summary = update_data["summary"]
    if "thumbnail_url" in update_data:
        record.thumbnail_url = update_data["thumbnail_url"]
    if "source_url" in update_data:
        record.source_url = update_data["source_url"]
    if "source_note" in update_data:
        record.source_note = update_data["source_note"]

    if "content_json" in update_data:
        normalized_json = normalize_content_json(update_data["content_json"])
        record.content_json = normalized_json
        if "content_html" not in update_data:
            record.content_html = _render_and_sanitize_html(normalized_json, None)

    if "content_html" in update_data:
        record.content_html = _render_and_sanitize_html(record.content_json, update_data["content_html"])

    if "status" in update_data:
        record.status = _normalize_news_status(update_data["status"])
        if record.status == "published" and not record.published_at:
            record.published_at = datetime.now(timezone.utc)
        if record.status != "published":
            record.published_at = None

    if "category_ids" in update_data and update_data["category_ids"] is not None:
        record.categories = _resolve_categories(db, update_data["category_ids"])

    if record.status == "published":
        _validate_publish_payload(record)

    if record.status == "published":
        if before_json != record.content_json or before_html != record.content_html:
            _create_version_snapshot(db, record, actor.id)

    db.add(record)
    db.commit()
    db.refresh(record)
    return _serialize_post(record)


def archive_admin_news(db: Session, post_id: int) -> dict[str, Any]:
    record = _get_post_or_404(db, post_id)
    record.status = "draft"
    record.published_at = None
    db.add(record)
    db.commit()
    db.refresh(record)
    return _serialize_post(record)


def publish_admin_news(db: Session, post_id: int, actor: AdminUser, force_generate_html: bool = True) -> dict[str, Any]:
    record = _get_post_or_404(db, post_id)
    record.slug = _build_slug(db, record.slug, title=record.title, exclude_id=record.id)

    if force_generate_html or not str(record.content_html or "").strip():
        record.content_html = _render_and_sanitize_html(record.content_json, None)
    else:
        record.content_html = _render_and_sanitize_html(record.content_json, record.content_html)

    _validate_publish_payload(record)

    if record.status == "published":
        _create_version_snapshot(db, record, actor.id)

    record.status = "published"
    record.published_at = datetime.now(timezone.utc)
    db.add(record)
    db.commit()
    db.refresh(record)
    return _serialize_post(record)


def unpublish_admin_news(db: Session, post_id: int) -> dict[str, Any]:
    record = _get_post_or_404(db, post_id)
    record.status = "draft"
    record.published_at = None
    db.add(record)
    db.commit()
    db.refresh(record)
    return _serialize_post(record)


def delete_admin_news(db: Session, post_id: int) -> None:
    record = _get_post_or_404(db, post_id)
    db.delete(record)
    db.commit()


async def upload_news_image(
    db: Session,
    actor: AdminUser,
    file: UploadFile,
    *,
    title: str | None,
    alt_text: str | None,
) -> dict[str, Any]:
    payload = await create_uploaded_media_asset(db=db, file=file, title=title, alt_text=alt_text)
    media_id = int(payload.get("id"))
    media = db.scalar(select(MediaAsset).where(MediaAsset.id == media_id))
    if not media:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Uploaded media is not available.")
    if media.asset_type != "image":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only image uploads are supported for news workflow.",
        )

    media.uploaded_by = actor.id
    db.add(media)
    db.commit()
    db.refresh(media)

    return {
        "id": media.id,
        "file_name": media.file_name,
        "file_url": media.url,
        "file_type": media.mime_type or "image/*",
        "file_size": media.size,
        "alt_text": media.alt_text,
        "uploaded_by": media.uploaded_by,
        "created_at": media.created_at.isoformat(),
    }


def list_news_images(db: Session, page: int, limit: int) -> dict[str, Any]:
    page = max(page, 1)
    limit = max(1, min(limit, 100))
    offset = (page - 1) * limit

    base_query = select(MediaAsset).where(MediaAsset.asset_type == "image")
    total = int(db.scalar(select(func.count(MediaAsset.id)).where(MediaAsset.asset_type == "image")) or 0)
    records = db.scalars(base_query.order_by(MediaAsset.created_at.desc(), MediaAsset.id.desc()).offset(offset).limit(limit)).all()

    items = [
        {
            "id": media.id,
            "file_name": media.file_name,
            "file_url": media.url,
            "file_type": media.mime_type or "image/*",
            "file_size": media.size,
            "alt_text": media.alt_text,
            "uploaded_by": media.uploaded_by,
            "created_at": media.created_at.isoformat(),
        }
        for media in records
    ]
    return {"items": items, "pagination": {"total": total, "page": page, "limit": limit}}


async def create_source_import_job(db: Session, payload: SourceImportCreatePayload, actor: AdminUser) -> dict[str, Any]:
    parsed = await fetch_source_and_parse(str(payload.source_url))
    record = SourceImportJob(
        source_url=str(payload.source_url),
        raw_title=parsed.get("title"),
        raw_html=parsed.get("raw_html"),
        raw_text=parsed.get("raw_text"),
        parsed_json=parsed.get("parsed_json"),
        status="completed",
        created_by=actor.id,
        created_at=datetime.now(timezone.utc),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return {
        "id": record.id,
        "source_url": record.source_url,
        "raw_title": record.raw_title,
        "raw_html": record.raw_html,
        "raw_text": record.raw_text,
        "parsed_json": record.parsed_json,
        "status": record.status,
        "created_by": record.created_by,
        "created_at": record.created_at.isoformat(),
        "source_note": payload.source_note,
        "policy_note": "Imported content is reference-only draft input and requires manual editorial review.",
    }


def get_source_import_job(db: Session, job_id: int) -> dict[str, Any]:
    job = db.scalar(select(SourceImportJob).where(SourceImportJob.id == job_id))
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import job not found.")
    return {
        "id": job.id,
        "source_url": job.source_url,
        "raw_title": job.raw_title,
        "raw_html": job.raw_html,
        "raw_text": job.raw_text,
        "parsed_json": job.parsed_json,
        "status": job.status,
        "created_by": job.created_by,
        "created_at": job.created_at.isoformat(),
    }


def apply_source_import_job(db: Session, job_id: int, payload: SourceImportApplyPayload) -> dict[str, Any]:
    job = db.scalar(select(SourceImportJob).where(SourceImportJob.id == job_id))
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import job not found.")

    parsed_json = normalize_content_json(job.parsed_json or {})

    if payload.post_id is None:
        return {
            "post_id": None,
            "content_json": parsed_json,
            "source_url": job.source_url,
            "source_note": payload.source_note,
            "status": "draft",
            "policy_note": "Apply to editor returns draft blocks only. Publishing remains a manual step.",
        }

    post = _get_post_or_404(db, payload.post_id)
    post.content_json = parsed_json
    post.content_html = _render_and_sanitize_html(parsed_json, None)
    post.source_url = job.source_url
    post.source_note = payload.source_note or post.source_note
    post.status = "draft"
    post.published_at = None
    db.add(post)
    db.commit()
    db.refresh(post)
    return {
        "post_id": post.id,
        "content_json": post.content_json,
        "source_url": post.source_url,
        "source_note": post.source_note,
        "status": post.status,
        "policy_note": "Source import is reference-only and requires manual editing before publishing.",
    }


def list_public_news(
    db: Session,
    *,
    page: int,
    limit: int,
    category_slug: str | None = None,
    skip: int | None = None,
) -> dict[str, Any]:
    limit = max(1, min(limit, 100))
    if skip is not None and skip >= 0:
        offset = skip
        page = max((skip // limit) + 1, 1)
    else:
        page = max(page, 1)
        offset = (page - 1) * limit

    filters = [NewsPost.status == "published"]
    normalized_category_slug = str(category_slug or "").strip().lower()
    if normalized_category_slug:
        filters.append(NewsPost.categories.any(NewsCategory.slug == normalized_category_slug))

    base_query = select(NewsPost).where(*filters)
    total = int(db.scalar(select(func.count(NewsPost.id)).where(*filters)) or 0)
    rows = db.scalars(
        base_query.order_by(NewsPost.published_at.desc().nullslast(), NewsPost.id.desc()).offset(offset).limit(limit)
    ).all()

    items: list[dict[str, Any]] = []
    for row in rows:
        serialized = _serialize_post(row)
        categories = serialized.get("categories") or []
        primary_category = categories[0] if categories else None
        items.append(
            {
                "id": serialized["id"],
                "title": serialized["title"],
                "slug": serialized["slug"],
                "summary": serialized["summary"],
                "thumbnail_url": serialized["thumbnail_url"],
                "published_at": serialized["published_at"],
                "created_at": serialized["created_at"],
                "category": primary_category,
                "categories": categories,
            }
        )

    return {
        "items": items,
        "pagination": {
            "total": total,
            "page": page,
            "limit": limit,
            "skip": offset,
        },
    }


def get_public_news_detail(db: Session, slug: str) -> dict[str, Any]:
    record = db.scalar(select(NewsPost).where(NewsPost.slug == slug, NewsPost.status == "published"))
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="News article not found.")
    return _serialize_post(record)
