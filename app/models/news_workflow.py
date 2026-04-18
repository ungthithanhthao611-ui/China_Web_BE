from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy import JSON as JSONType
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BIGINT_TYPE, Base
from app.models.mixins import BigIntPrimaryKeyMixin, TimestampMixin

JSON_COLUMN = JSONType().with_variant(JSONB, "postgresql")


class NewsPost(BigIntPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "news_posts"

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    thumbnail_url: Mapped[str | None] = mapped_column(String(1000))
    content_json: Mapped[dict | None] = mapped_column(JSON_COLUMN)
    content_html: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(String(2000))
    source_note: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(50), default="draft", index=True, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    author_id: Mapped[int | None] = mapped_column(ForeignKey("admin_users.id"), index=True)

    author = relationship("AdminUser")
    categories = relationship("NewsCategory", secondary="news_post_categories", lazy="selectin")
    versions = relationship("NewsPostVersion", back_populates="post", lazy="selectin")


class NewsCategory(BigIntPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "news_categories"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)


class NewsPostCategory(BigIntPrimaryKeyMixin, Base):
    __tablename__ = "news_post_categories"
    __table_args__ = (
        Index("ix_news_post_categories_post_category", "post_id", "category_id", unique=True),
    )

    post_id: Mapped[int] = mapped_column(ForeignKey("news_posts.id", ondelete="CASCADE"), index=True, nullable=False)
    category_id: Mapped[int] = mapped_column(
        ForeignKey("news_categories.id", ondelete="CASCADE"), index=True, nullable=False
    )


class NewsPostVersion(BigIntPrimaryKeyMixin, Base):
    __tablename__ = "news_post_versions"
    __table_args__ = (Index("ix_news_post_versions_post_version", "post_id", "version_no", unique=True),)

    post_id: Mapped[int] = mapped_column(ForeignKey("news_posts.id", ondelete="CASCADE"), index=True, nullable=False)
    version_no: Mapped[int] = mapped_column(nullable=False)
    content_json: Mapped[dict | None] = mapped_column(JSON_COLUMN)
    content_html: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("admin_users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    post = relationship("NewsPost", back_populates="versions")
    creator = relationship("AdminUser")


class SourceImportJob(BigIntPrimaryKeyMixin, Base):
    __tablename__ = "source_import_jobs"

    source_url: Mapped[str] = mapped_column(String(2000), nullable=False)
    raw_title: Mapped[str | None] = mapped_column(String(500))
    raw_html: Mapped[str | None] = mapped_column(Text)
    raw_text: Mapped[str | None] = mapped_column(Text)
    parsed_json: Mapped[dict | None] = mapped_column(JSON_COLUMN)
    status: Mapped[str] = mapped_column(String(50), default="completed", index=True, nullable=False)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("admin_users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    creator = relationship("AdminUser")
