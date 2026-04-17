from __future__ import annotations

import base64
import hashlib
from datetime import datetime, timezone
from typing import Any

import httpx
from bs4 import BeautifulSoup
from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.media import MediaAsset
from app.models.news import Post, PostCategory
from app.models.taxonomy import Language
from app.schemas.wordpress_sync import WordPressSyncRequest, WordPressSyncResult

CANONICAL_CATEGORY_NAMES = {
    "corporate-news": "Corporate News",
    "industry-dynamics": "Industry dynamics",
}


def _normalize_base_url(base_url: str) -> str:
    normalized = base_url.strip().rstrip("/")
    if not normalized:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="WP_BASE_URL is empty. Please configure WordPress connection settings.",
        )
    return normalized


def _auth_header() -> dict[str, str]:
    username = settings.wp_username.strip()
    app_password = settings.wp_app_password.strip()
    if not username or not app_password:
        return {}
    token = base64.b64encode(f"{username}:{app_password}".encode("utf-8")).decode("ascii")
    return {"Authorization": f"Basic {token}"}


def _wp_endpoint_url(endpoint: str) -> str:
    base_url = _normalize_base_url(settings.wp_base_url)
    clean_endpoint = endpoint.strip().lstrip("/")
    return f"{base_url}/wp-json/wp/v2/{clean_endpoint}"


def _resolve_wp_auth_header(*, required: bool) -> dict[str, str]:
    auth_header = _auth_header()
    if not required:
        return auth_header
    if auth_header:
        return auth_header
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="WordPress delete sync requires WP_USERNAME and WP_APP_PASSWORD.",
    )


def _raise_wp_api_error(response: httpx.Response, endpoint: str) -> None:
    if response.status_code == 401:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="WordPress authentication failed. Check WP_USERNAME and WP_APP_PASSWORD.",
        )
    if response.status_code == 403:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="WordPress account does not have enough permissions for delete sync.",
        )
    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=f"WordPress API error ({response.status_code}) on {endpoint}: {response.text[:300]}",
    )


def _wp_posts_lookup_params(slug: str) -> dict[str, Any]:
    return {
        "slug": slug,
        "per_page": 100,
        "context": "edit",
        "status": "any",
    }


def _delete_wordpress_post_by_id_sync(
    client: httpx.Client,
    *,
    wp_post_id: int,
    headers: dict[str, str],
) -> bool:
    response = client.delete(
        _wp_endpoint_url(f"posts/{wp_post_id}"),
        headers=headers,
        params={"force": "true"},
    )
    if response.status_code in {200, 410, 404}:
        return response.status_code != 404
    _raise_wp_api_error(response, f"posts/{wp_post_id}")
    return False


def delete_wordpress_post(
    *,
    wp_post_id: int | None = None,
    slug: str | None = None,
) -> int:
    if not settings.wp_bidirectional_delete_enabled:
        return 0

    auth_header = _resolve_wp_auth_header(required=True)
    headers = {"Accept": "application/json", **auth_header}
    deleted_count = 0
    normalized_slug = _slugify(slug, fallback="") if slug else ""

    try:
        with httpx.Client(timeout=httpx.Timeout(30.0, connect=10.0), follow_redirects=True) as client:
            if wp_post_id:
                deleted_by_id = _delete_wordpress_post_by_id_sync(client, wp_post_id=wp_post_id, headers=headers)
                if deleted_by_id or not normalized_slug:
                    return 1 if deleted_by_id else 0

            if not normalized_slug:
                return 0

            lookup_response = client.get(
                _wp_endpoint_url("posts"),
                headers=headers,
                params=_wp_posts_lookup_params(normalized_slug),
            )
            if lookup_response.status_code == 400:
                lookup_response = client.get(
                    _wp_endpoint_url("posts"),
                    headers=headers,
                    params={
                        "slug": normalized_slug,
                        "per_page": 100,
                        "context": "edit",
                        "status": "publish,draft,pending,private,future,trash",
                    },
                )
            if lookup_response.status_code >= 400:
                _raise_wp_api_error(lookup_response, "posts")

            payload = lookup_response.json()
            if not isinstance(payload, list):
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="WordPress API returned unexpected response for posts lookup.",
                )

            for item in payload:
                candidate_id = int(item.get("id") or 0)
                if not candidate_id:
                    continue
                if _delete_wordpress_post_by_id_sync(client, wp_post_id=candidate_id, headers=headers):
                    deleted_count += 1
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Cannot reach WordPress API while deleting post: {exc}",
        ) from exc

    return deleted_count


def _plain_text(html: str | None) -> str:
    if not html:
        return ""
    return BeautifulSoup(html, "html.parser").get_text(" ", strip=True)


def _slugify(value: str | None, fallback: str) -> str:
    raw = (value or "").strip().lower()
    if not raw:
        raw = fallback
    parts: list[str] = []
    current: list[str] = []
    for character in raw:
        if character.isalnum():
            current.append(character)
            continue
        if current:
            parts.append("".join(current))
            current = []
    if current:
        parts.append("".join(current))
    return "-".join(parts) or fallback


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _category_slug_aliases() -> dict[str, str]:
    aliases: dict[str, str] = {}
    raw_value = settings.wp_category_slug_aliases.strip()
    if not raw_value:
        return aliases

    for segment in raw_value.split(","):
        normalized_segment = segment.strip()
        if not normalized_segment or ":" not in normalized_segment:
            continue
        source, target = normalized_segment.split(":", 1)
        source_slug = _slugify(source, fallback="")
        target_slug = _slugify(target, fallback="")
        if source_slug and target_slug:
            aliases[source_slug] = target_slug
    return aliases


def _resolve_language(db: Session, language_code: str) -> Language:
    language = db.scalar(select(Language).where(Language.code == language_code))
    if language:
        return language
    fallback = db.scalar(select(Language).where(Language.is_default.is_(True)))
    if fallback:
        return fallback
    fallback = db.scalar(select(Language).order_by(Language.id.asc()))
    if fallback:
        return fallback
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="No language records found. Initialize base data first.",
    )


def _category_by_wp_id(
    categories_payload: list[dict[str, Any]],
    result: WordPressSyncResult,
    db: Session,
) -> dict[int, PostCategory]:
    category_mapping: dict[int, PostCategory] = {}
    alias_map = _category_slug_aliases()
    existing_by_slug = {
        category.slug: category
        for category in db.scalars(select(PostCategory)).all()
    }

    for source_slug, target_slug in alias_map.items():
        if source_slug == target_slug:
            continue
        source_record = existing_by_slug.get(source_slug)
        if source_record is None:
            continue

        target_record = existing_by_slug.get(target_slug)
        if target_record is None:
            target_record = PostCategory(
                name=CANONICAL_CATEGORY_NAMES.get(target_slug, target_slug.replace("-", " ").title()),
                slug=target_slug,
                description=f"Canonical category mapped from '{source_slug}'.",
                status="active",
            )
            db.add(target_record)
            db.flush()
            existing_by_slug[target_slug] = target_record
            result.categories_created += 1

        if source_record.id != target_record.id:
            db.execute(
                update(Post)
                .where(Post.category_id == source_record.id)
                .values(category_id=target_record.id)
            )
        if source_record.status != "inactive":
            source_record.status = "inactive"
            db.add(source_record)
            result.categories_updated += 1

    for item in categories_payload:
        wp_id = int(item.get("id") or 0)
        if not wp_id:
            continue

        name = str(item.get("name") or "").strip() or f"WP Category {wp_id}"
        source_slug = _slugify(str(item.get("slug") or name), fallback=f"wp-category-{wp_id}")
        slug = alias_map.get(source_slug, source_slug)
        description = str(item.get("description") or "").strip() or None

        record = existing_by_slug.get(slug)
        if record is None:
            record = PostCategory(
                name=CANONICAL_CATEGORY_NAMES.get(slug, name),
                slug=slug,
                description=description,
                status="active",
            )
            db.add(record)
            db.flush()
            result.categories_created += 1
        else:
            changed = False
            target_name = CANONICAL_CATEGORY_NAMES.get(slug, name)
            if record.name != target_name:
                record.name = target_name
                changed = True
            if record.description != description:
                record.description = description
                changed = True
            if record.status != "active":
                record.status = "active"
                changed = True
            if changed:
                db.add(record)
                result.categories_updated += 1

        category_mapping[wp_id] = record
        existing_by_slug[slug] = record

    return category_mapping


def _media_from_featured(
    db: Session,
    featured_media: dict[str, Any] | None,
    result: WordPressSyncResult,
) -> MediaAsset | None:
    if not featured_media:
        return None

    media_id = int(featured_media.get("id") or 0)
    media_url = str(featured_media.get("source_url") or "").strip()
    if not media_url:
        return None

    if media_id:
        media_uuid = f"wp-media-{media_id}"
    else:
        media_uuid = f"wp-media-{hashlib.sha1(media_url.encode('utf-8')).hexdigest()[:16]}"

    file_name = media_url.rsplit("/", 1)[-1][:255] or None
    mime_type = str(featured_media.get("mime_type") or "").strip() or None
    title_html = (featured_media.get("title") or {}).get("rendered") if isinstance(featured_media.get("title"), dict) else None
    alt_text = str(featured_media.get("alt_text") or "").strip() or None
    media_title = _plain_text(title_html) or file_name

    record = db.scalar(select(MediaAsset).where(MediaAsset.uuid == media_uuid))
    if record is None:
        record = MediaAsset(
            uuid=media_uuid,
            file_name=file_name,
            url=media_url,
            storage_path=f"wp://media/{media_id}" if media_id else None,
            asset_type="image",
            mime_type=mime_type,
            alt_text=alt_text,
            title=media_title,
            status="active",
        )
        db.add(record)
        db.flush()
        result.media_created += 1
        return record

    changed = False
    if record.url != media_url:
        record.url = media_url
        changed = True
    if record.file_name != file_name:
        record.file_name = file_name
        changed = True
    if record.mime_type != mime_type:
        record.mime_type = mime_type
        changed = True
    if record.alt_text != alt_text:
        record.alt_text = alt_text
        changed = True
    if record.title != media_title:
        record.title = media_title
        changed = True
    if record.status != "active":
        record.status = "active"
        changed = True
    if changed:
        db.add(record)
        result.media_updated += 1
    return record


async def _fetch_wp_paginated(
    endpoint: str,
    *,
    per_page: int,
    max_pages: int,
    params: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    base_url = _normalize_base_url(settings.wp_base_url)
    url = f"{base_url}/wp-json/wp/v2/{endpoint}"
    headers = {"Accept": "application/json", **_auth_header()}
    all_items: list[dict[str, Any]] = []

    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0), follow_redirects=True) as client:
        for page in range(1, max_pages + 1):
            request_params = {"page": page, "per_page": per_page, **(params or {})}
            response = await client.get(url, headers=headers, params=request_params)
            if response.status_code == 400 and page > 1:
                break
            if response.status_code == 401:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="WordPress authentication failed. Check WP_USERNAME and WP_APP_PASSWORD.",
                )
            if response.status_code >= 400:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"WordPress API error ({response.status_code}) on {endpoint}: {response.text[:300]}",
                )

            payload = response.json()
            if not isinstance(payload, list):
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"WordPress API returned unexpected response for {endpoint}.",
                )
            if not payload:
                break
            all_items.extend(payload)
    return all_items


async def _fetch_wp_post_status_by_id(
    client: httpx.AsyncClient,
    *,
    wp_post_id: int,
    headers: dict[str, str],
) -> str | None:
    response = await client.get(
        _wp_endpoint_url(f"posts/{wp_post_id}"),
        headers=headers,
        params={"context": "edit"},
    )

    if response.status_code == 404:
        return None
    if response.status_code >= 400:
        _raise_wp_api_error(response, f"posts/{wp_post_id}")

    payload = response.json()
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"WordPress API returned unexpected response for posts/{wp_post_id}.",
        )

    wp_status = str(payload.get("status") or "").strip().lower()
    if wp_status == "trash":
        return None
    return wp_status or "publish"


async def _prune_deleted_wordpress_posts(
    db: Session,
    *,
    language: Language,
    fetched_posts: list[dict[str, Any]],
    result: WordPressSyncResult,
) -> None:
    if not settings.wp_bidirectional_delete_enabled:
        return

    auth_header = _auth_header()
    if not auth_header:
        result.errors.append("Skipped delete sync: missing WP_USERNAME/WP_APP_PASSWORD.")
        return

    fetched_wp_ids = {int(item.get("id") or 0) for item in fetched_posts if int(item.get("id") or 0)}

    wp_posts = db.scalars(
        select(Post).where(
            Post.language_id == language.id,
            Post.source_system == "wordpress",
            Post.wp_post_id.is_not(None),
        )
    ).all()
    if not wp_posts:
        return

    candidates = [item for item in wp_posts if int(item.wp_post_id or 0) not in fetched_wp_ids]
    if not candidates:
        return

    headers = {"Accept": "application/json", **auth_header}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0), follow_redirects=True) as client:
            for local_post in candidates:
                wp_post_id = int(local_post.wp_post_id or 0)
                if not wp_post_id:
                    continue
                remote_status = await _fetch_wp_post_status_by_id(
                    client,
                    wp_post_id=wp_post_id,
                    headers=headers,
                )
                if remote_status is None:
                    db.delete(local_post)
                    result.posts_deleted += 1
    except HTTPException:
        raise
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Cannot reach WordPress API while pruning deleted posts: {exc}",
        ) from exc


def _extract_featured_media(post_payload: dict[str, Any]) -> dict[str, Any] | None:
    embedded = post_payload.get("_embedded")
    if not isinstance(embedded, dict):
        return None
    featured_items = embedded.get("wp:featuredmedia")
    if not isinstance(featured_items, list) or not featured_items:
        return None
    first_item = featured_items[0]
    if not isinstance(first_item, dict):
        return None
    return first_item


def _extract_author_name(post_payload: dict[str, Any]) -> str | None:
    embedded = post_payload.get("_embedded")
    if not isinstance(embedded, dict):
        return None
    author_items = embedded.get("author")
    if not isinstance(author_items, list) or not author_items:
        return None
    first_item = author_items[0]
    if not isinstance(first_item, dict):
        return None
    name = str(first_item.get("name") or "").strip()
    return name or None


def _resolve_default_category(db: Session) -> PostCategory | None:
    default_slug = _slugify(settings.wp_default_category_slug, fallback="corporate-news")
    record = db.scalar(select(PostCategory).where(PostCategory.slug == default_slug))
    if record:
        return record

    fallback_name = CANONICAL_CATEGORY_NAMES.get(default_slug, default_slug.replace("-", " ").title())
    record = PostCategory(
        name=fallback_name,
        slug=default_slug,
        description="Default category for imported WordPress posts.",
        status="active",
    )
    db.add(record)
    db.flush()
    return record


async def sync_wordpress_posts(
    db: Session,
    payload: WordPressSyncRequest,
) -> WordPressSyncResult:
    result = WordPressSyncResult()
    language = _resolve_language(db, payload.language_code)
    default_category = _resolve_default_category(db)

    categories = await _fetch_wp_paginated(
        "categories",
        per_page=min(payload.per_page, 100),
        max_pages=payload.max_pages,
    )
    categories_by_wp_id = _category_by_wp_id(categories, result, db)

    posts = await _fetch_wp_paginated(
        "posts",
        per_page=payload.per_page,
        max_pages=payload.max_pages,
        params={"_embed": 1, "status": payload.status},
    )
    result.fetched_posts = len(posts)

    existing_posts_by_slug = {item.slug: item for item in db.scalars(select(Post)).all()}

    for item in posts:
        try:
            wp_id = int(item.get("id") or 0)
            title_html = (item.get("title") or {}).get("rendered") if isinstance(item.get("title"), dict) else None
            content_html = (item.get("content") or {}).get("rendered") if isinstance(item.get("content"), dict) else None
            excerpt_html = (item.get("excerpt") or {}).get("rendered") if isinstance(item.get("excerpt"), dict) else None

            title = _plain_text(title_html) or f"WordPress Post {wp_id or 'Unknown'}"
            slug = _slugify(str(item.get("slug") or title), fallback=f"wp-post-{wp_id or len(existing_posts_by_slug)+1}")
            summary = _plain_text(excerpt_html) or None
            body = str(content_html or "")
            author_name = _extract_author_name(item)
            meta_description = (summary or _plain_text(content_html) or "")[:160] or None
            published_at = _parse_datetime(str(item.get("date_gmt") or item.get("date") or ""))

            wp_status = str(item.get("status") or "publish").strip().lower()
            local_status = "published" if wp_status == "publish" else "draft"

            category_id = None
            wp_category_ids = item.get("categories") or []
            if isinstance(wp_category_ids, list):
                for wp_category_id in wp_category_ids:
                    category = categories_by_wp_id.get(int(wp_category_id))
                    if category:
                        category_id = category.id
                        break
            if category_id is None and default_category is not None:
                category_id = default_category.id

            media = _media_from_featured(db, _extract_featured_media(item), result)

            record = existing_posts_by_slug.get(slug)
            if record is None:
                record = Post(
                    category_id=category_id,
                    title=title[:255],
                    slug=slug,
                    summary=summary,
                    body=body,
                    wp_post_id=wp_id or None,
                    source_system="wordpress",
                    published_at=published_at,
                    author=author_name,
                    image_id=media.id if media else None,
                    language_id=language.id,
                    status=local_status,
                    meta_title=title[:255],
                    meta_description=meta_description,
                )
                db.add(record)
                db.flush()
                existing_posts_by_slug[slug] = record
                result.posts_created += 1
                continue

            changed = False
            for field_name, value in [
                ("category_id", category_id),
                ("title", title[:255]),
                ("summary", summary),
                ("body", body),
                ("wp_post_id", wp_id or None),
                ("source_system", "wordpress"),
                ("published_at", published_at),
                ("author", author_name),
                ("image_id", media.id if media else None),
                ("language_id", language.id),
                ("status", local_status),
                ("meta_title", title[:255]),
                ("meta_description", meta_description),
            ]:
                if getattr(record, field_name) != value:
                    setattr(record, field_name, value)
                    changed = True
            if changed:
                db.add(record)
                result.posts_updated += 1
        except Exception as exc:
            post_label = str(item.get("slug") or item.get("id") or "unknown")
            result.errors.append(f"Post {post_label}: {exc}")

    await _prune_deleted_wordpress_posts(
        db,
        language=language,
        fetched_posts=posts,
        result=result,
    )

    db.commit()
    return result
