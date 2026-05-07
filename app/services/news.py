import json
import time
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.news import NewsPost
from app.schemas.news import NewsPostRead
from app.utils.news_blocks import render_content_json_to_html


def _serialize(schema: type, record: Any) -> dict[str, Any]:
    return schema.model_validate(record).model_dump(mode="json")


def _parse_content_json(raw_value: Any) -> dict[str, Any] | None:
    if raw_value is None:
        return None
    if isinstance(raw_value, dict):
        return raw_value
    if isinstance(raw_value, str):
        normalized = raw_value.strip()
        if not normalized:
            return None
        try:
            parsed = json.loads(normalized)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


def _apply_localized_fields(payload: dict[str, Any], language_code: str) -> dict[str, Any]:
    if language_code == "vi":
        return payload

    suffix = f"_{language_code}"
    for field in ["title", "summary", "content", "meta_title", "meta_description"]:
        localized = payload.get(f"{field}{suffix}")
        if localized and str(localized).strip():
            payload[field] = localized

    if payload.get(f"content{suffix}") and str(payload.get(f"content{suffix}") or "").strip():
        payload["content_json"] = None

    return payload


def _serialize_public_post(record: NewsPost, language_code: str = "vi") -> dict[str, Any]:
    payload = _serialize(NewsPostRead, record)
    payload = _apply_localized_fields(payload, language_code)
    parsed_content_json = _parse_content_json(payload.get("content_json"))
    rendered_html = render_content_json_to_html(parsed_content_json) if parsed_content_json else ""
    fallback_content = payload.get("content") or ""
    payload["content_html"] = rendered_html or fallback_content
    if payload.get("published_at") is None:
        payload["published_at"] = payload.get("created_at")
    return payload


_PUBLIC_NEWS_CACHE: dict[str, dict[str, Any]] = {}
_PUBLIC_NEWS_CACHE_TTL = 120


def _build_news_cache_key(
    *,
    skip: int,
    limit: int,
    keyword: str | None,
    status: str | None,
    language_code: str,
) -> str:
    normalized_keyword = str(keyword or "").strip().lower()
    normalized_status = str(status or "").strip().lower()
    normalized_language = str(language_code or "vi").strip().lower() or "vi"
    return "::".join(
        [
            "news",
            normalized_language,
            normalized_status or "__all__",
            normalized_keyword or "__none__",
            str(skip),
            str(limit),
        ]
    )


def list_news_posts(
    db: Session,
    *,
    skip: int = 0,
    limit: int = 12,
    keyword: str | None = None,
    status: str | None = None,
    language_code: str = "vi",
) -> dict[str, Any]:
    """Danh sách bài viết public (chỉ published, chưa soft-delete)."""
    cache_key = _build_news_cache_key(
        skip=skip,
        limit=limit,
        keyword=keyword,
        status=status,
        language_code=language_code,
    )
    cached_payload = _PUBLIC_NEWS_CACHE.get(cache_key)
    if cached_payload is not None:
        if time.time() - cached_payload["timestamp"] < _PUBLIC_NEWS_CACHE_TTL:
            return cached_payload["data"]
        _PUBLIC_NEWS_CACHE.pop(cache_key, None)

    query = select(NewsPost).where(
        NewsPost.status == "published",
        NewsPost.deleted_at.is_(None),
    )
    count_query = select(func.count()).select_from(NewsPost).where(
        NewsPost.status == "published",
        NewsPost.deleted_at.is_(None),
    )

    if keyword:
        like_pattern = f"%{keyword}%"
        query = query.where(NewsPost.title.ilike(like_pattern))
        count_query = count_query.where(NewsPost.title.ilike(like_pattern))

    total = db.scalar(count_query) or 0

    posts = db.scalars(
        query.order_by(NewsPost.published_at.desc(), NewsPost.created_at.desc())
        .offset(skip)
        .limit(limit)
    ).all()

    payload = {
        "items": [_serialize_public_post(p, language_code=language_code) for p in posts],
        "total": total,
        "skip": skip,
        "limit": limit,
    }
    _PUBLIC_NEWS_CACHE[cache_key] = {
        "data": payload,
        "timestamp": time.time(),
    }
    return payload


def get_news_post_detail(db: Session, *, slug: str, language_code: str = "vi") -> dict[str, Any]:
    """Chi tiết bài viết public theo slug."""
    post = db.scalar(
        select(NewsPost).where(
            NewsPost.slug == slug,
            NewsPost.status == "published",
            NewsPost.deleted_at.is_(None),
        )
    )
    if not post:
        return None
    return _serialize_public_post(post, language_code=language_code)


def list_admin_news_posts(
    db: Session,
    *,
    skip: int = 0,
    limit: int = 20,
    keyword: str | None = None,
    status: str | None = None,
    include_deleted: bool = False,
) -> dict[str, Any]:
    """Danh sách bài viết cho admin (bao gồm tất cả status)."""
    query = select(NewsPost)
    count_query = select(func.count()).select_from(NewsPost)

    if not include_deleted:
        query = query.where(NewsPost.deleted_at.is_(None))
        count_query = count_query.where(NewsPost.deleted_at.is_(None))

    if keyword:
        like_pattern = f"%{keyword}%"
        query = query.where(NewsPost.title.ilike(like_pattern))
        count_query = count_query.where(NewsPost.title.ilike(like_pattern))

    if status:
        query = query.where(NewsPost.status == status)
        count_query = count_query.where(NewsPost.status == status)

    total = db.scalar(count_query) or 0

    posts = db.scalars(
        query.order_by(NewsPost.created_at.desc())
        .offset(skip)
        .limit(limit)
    ).all()

    return {
        "items": [_serialize(NewsPostRead, p) for p in posts],
        "total": total,
        "skip": skip,
        "limit": limit,
    }
