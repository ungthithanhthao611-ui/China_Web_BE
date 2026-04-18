from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

NewsStatus = Literal["draft", "published"]
BlockType = Literal["text", "heading", "image", "gallery", "quote", "divider", "two_column"]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class NewsPageConfig(BaseModel):
    width: int = Field(default=900, ge=600, le=1600)
    background: str = Field(default="#ffffff", min_length=1, max_length=30)


class NewsEditorBlock(BaseModel):
    id: str = Field(min_length=1, max_length=120)
    type: BlockType
    x: int = Field(default=40, ge=0, le=5000)
    y: int = Field(default=40, ge=0, le=50000)
    w: int = Field(default=720, ge=80, le=5000)
    h: int = Field(default=120, ge=24, le=50000)
    content: str = ""
    props: dict[str, Any] = Field(default_factory=dict)


class NewsContentJson(BaseModel):
    page: NewsPageConfig = Field(default_factory=NewsPageConfig)
    blocks: list[NewsEditorBlock] = Field(default_factory=list)


class NewsPostPayload(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    slug: str | None = Field(default=None, min_length=1, max_length=255)
    summary: str | None = Field(default=None, max_length=2000)
    thumbnail_url: str | None = Field(default=None, max_length=2000)
    content_json: NewsContentJson = Field(default_factory=NewsContentJson)
    content_html: str | None = None
    source_url: str | None = Field(default=None, max_length=2000)
    source_note: str | None = Field(default=None, max_length=4000)
    status: NewsStatus = "draft"
    category_ids: list[int] = Field(default_factory=list)

    @field_validator("slug")
    @classmethod
    def normalize_slug(cls, value: str | None) -> str | None:
        if value is None:
            return value
        stripped = value.strip()
        return stripped or None


class NewsPostUpdatePayload(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    slug: str | None = Field(default=None, min_length=1, max_length=255)
    summary: str | None = Field(default=None, max_length=2000)
    thumbnail_url: str | None = Field(default=None, max_length=2000)
    content_json: NewsContentJson | None = None
    content_html: str | None = None
    source_url: str | None = Field(default=None, max_length=2000)
    source_note: str | None = Field(default=None, max_length=4000)
    status: NewsStatus | None = None
    category_ids: list[int] | None = None


class NewsPostListQuery(BaseModel):
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=10, ge=1, le=100)
    keyword: str | None = Field(default=None, max_length=200)
    status: NewsStatus | None = None
    category_id: int | None = Field(default=None, ge=1)


class NewsPostListItem(BaseModel):
    id: int
    title: str
    slug: str
    summary: str | None = None
    thumbnail_url: str | None = None
    status: NewsStatus
    published_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class NewsCategoryRead(ORMModel):
    id: int
    name: str
    slug: str
    description: str | None


class NewsCategoryOptionRead(BaseModel):
    id: int
    name: str
    slug: str
    description: str | None = None


class NewsPostRead(BaseModel):
    id: int
    title: str
    slug: str
    summary: str | None = None
    thumbnail_url: str | None = None
    content_json: dict[str, Any] | None = None
    content_html: str | None = None
    source_url: str | None = None
    source_note: str | None = None
    status: NewsStatus
    published_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    category_ids: list[int] = Field(default_factory=list)


class NewsPostVersionRead(BaseModel):
    id: int
    post_id: int
    version_no: int
    content_json: dict[str, Any] | None = None
    content_html: str | None = None
    created_by: int | None = None
    created_at: datetime


class NewsPublishPayload(BaseModel):
    force_generate_html: bool = True


class MediaImageRead(BaseModel):
    id: int
    file_name: str | None = None
    file_url: str
    file_type: str
    file_size: int | None = None
    alt_text: str | None = None
    uploaded_by: int | None = None
    created_at: datetime


class SourceImportCreatePayload(BaseModel):
    source_url: HttpUrl
    source_note: str | None = Field(default=None, max_length=4000)


class SourceImportApplyPayload(BaseModel):
    post_id: int | None = None
    source_note: str | None = Field(default=None, max_length=4000)


class SourceImportJobRead(BaseModel):
    id: int
    source_url: str
    raw_title: str | None = None
    raw_html: str | None = None
    raw_text: str | None = None
    parsed_json: dict[str, Any] | None = None
    status: str
    created_by: int | None = None
    created_at: datetime
