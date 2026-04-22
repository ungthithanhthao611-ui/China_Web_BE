from datetime import datetime

from pydantic import BaseModel

from app.schemas.entities import ORMModel


class NewsPostCreate(BaseModel):
    title: str
    slug: str
    summary: str | None = None
    content: str | None = None
    content_json: str | None = None
    thumbnail_url: str | None = None
    image_id: int | None = None
    author: str | None = None
    status: str = "draft"
    is_featured: bool = False
    published_at: datetime | None = None
    meta_title: str | None = None
    meta_description: str | None = None
    sort_order: int = 0


class NewsPostUpdate(BaseModel):
    title: str | None = None
    slug: str | None = None
    summary: str | None = None
    content: str | None = None
    content_json: str | None = None
    thumbnail_url: str | None = None
    image_id: int | None = None
    author: str | None = None
    status: str | None = None
    is_featured: bool | None = None
    published_at: datetime | None = None
    deleted_at: datetime | None = None
    meta_title: str | None = None
    meta_description: str | None = None
    sort_order: int | None = None


class NewsPostRead(ORMModel):
    id: int
    title: str
    slug: str
    summary: str | None
    content: str | None
    content_json: str | None
    thumbnail_url: str | None
    image_id: int | None
    author: str | None
    status: str
    is_featured: bool
    published_at: datetime | None
    deleted_at: datetime | None
    meta_title: str | None
    meta_description: str | None
    sort_order: int
    created_at: datetime
    updated_at: datetime
