from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, BIGINT_TYPE
from app.models.mixins import BigIntPrimaryKeyMixin, SortOrderMixin, StatusMixin, TimestampMixin


class NewsCategory(BigIntPrimaryKeyMixin, TimestampMixin, SortOrderMixin, Base):
    __tablename__ = "news_categories"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    parent_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("news_categories.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="active", nullable=False)

    posts = relationship("NewsPost", back_populates="category")


class NewsPost(BigIntPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "news_posts"

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    slug: Mapped[str] = mapped_column(String(500), unique=True, nullable=False, index=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    content_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    thumbnail_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    image_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    category_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("news_categories.id"), nullable=True)
    author: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="draft", index=True, nullable=False)
    is_featured: Mapped[bool] = mapped_column(default=False, nullable=False)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    meta_title: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    meta_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    category = relationship("NewsCategory", back_populates="posts")
