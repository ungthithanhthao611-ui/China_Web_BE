from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.news import NewsCategory, NewsPost
from app.schemas.news import NewsCategoryRead, NewsPostRead


def _serialize(schema: type, record: Any) -> dict[str, Any]:
    return schema.model_validate(record).model_dump(mode="json")


def list_news_posts(
    db: Session,
    *,
    skip: int = 0,
    limit: int = 12,
    keyword: str | None = None,
    category_slug: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    """Danh sách bài viết public (chỉ published, chưa soft-delete)."""
    query = select(NewsPost).options(selectinload(NewsPost.category)).where(
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

    if category_slug:
        cat = db.scalar(select(NewsCategory).where(NewsCategory.slug == category_slug))
        if cat:
            query = query.where(NewsPost.category_id == cat.id)
            count_query = count_query.where(NewsPost.category_id == cat.id)
        else:
            return {
                "items": [],
                "total": 0,
                "skip": skip,
                "limit": limit,
            }

    total = db.scalar(count_query) or 0

    posts = db.scalars(
        query.order_by(NewsPost.published_at.desc(), NewsPost.created_at.desc())
        .offset(skip)
        .limit(limit)
    ).all()

    return {
        "items": [_serialize(NewsPostRead, p) for p in posts],
        "total": total,
        "skip": skip,
        "limit": limit,
    }


def get_news_post_detail(db: Session, *, slug: str) -> dict[str, Any]:
    """Chi tiết bài viết public theo slug."""
    post = db.scalar(
        select(NewsPost)
        .options(selectinload(NewsPost.category))
        .where(
            NewsPost.slug == slug,
            NewsPost.status == "published",
            NewsPost.deleted_at.is_(None),
        )
    )
    if not post:
        return None
    return _serialize(NewsPostRead, post)


def list_news_categories(db: Session) -> list[dict[str, Any]]:
    """Danh sách danh mục tin tức public."""
    cats = db.scalars(
        select(NewsCategory)
        .where(NewsCategory.status == "active")
        .order_by(NewsCategory.sort_order)
    ).all()
    return [_serialize(NewsCategoryRead, c) for c in cats]


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
    query = select(NewsPost).options(selectinload(NewsPost.category))
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
