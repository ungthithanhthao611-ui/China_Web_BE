from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import BigIntPrimaryKeyMixin, SortOrderMixin, TimestampMixin


class Video(BigIntPrimaryKeyMixin, TimestampMixin, SortOrderMixin, Base):
    __tablename__ = "videos"

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    # Keep this generous because CDN/transformed URLs can be long.
    video_url: Mapped[str] = mapped_column(String(2000), nullable=False)
    thumbnail_id: Mapped[int | None] = mapped_column(ForeignKey("media_assets.id"))
    language_id: Mapped[int] = mapped_column(ForeignKey("languages.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="published", index=True, nullable=False)

    thumbnail = relationship("MediaAsset")


class Branch(BigIntPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "branches"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    branch_type: Mapped[str | None] = mapped_column(String(100), index=True)
    address: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(String(100))
    region: Mapped[str | None] = mapped_column(String(100))
    phone: Mapped[str | None] = mapped_column(String(100))
    email: Mapped[str | None] = mapped_column(String(150))
    map_url: Mapped[str | None] = mapped_column(String(500))
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("branches.id"))
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    language_id: Mapped[int] = mapped_column(ForeignKey("languages.id"), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    body: Mapped[str | None] = mapped_column(Text)
    image_id: Mapped[int | None] = mapped_column(ForeignKey("media_assets.id"))
    hero_image_id: Mapped[int | None] = mapped_column(ForeignKey("media_assets.id"))
    meta_title: Mapped[str | None] = mapped_column(String(255))
    meta_description: Mapped[str | None] = mapped_column(String(500))

    image = relationship("MediaAsset", foreign_keys=[image_id])
    hero_image = relationship("MediaAsset", foreign_keys=[hero_image_id])


class Contact(BigIntPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "contacts"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    contact_type: Mapped[str | None] = mapped_column(String(100), index=True)
    address: Mapped[str | None] = mapped_column(Text)
    postal_code: Mapped[str | None] = mapped_column(String(20))
    phone: Mapped[str | None] = mapped_column(String(100))
    email: Mapped[str | None] = mapped_column(String(150))
    map_url: Mapped[str | None] = mapped_column(String(500))
    latitude: Mapped[str | None] = mapped_column(String(30))
    longitude: Mapped[str | None] = mapped_column(String(30))
    branch_id: Mapped[int | None] = mapped_column(ForeignKey("branches.id"))
    is_primary: Mapped[bool] = mapped_column(default=False, nullable=False)
    language_id: Mapped[int] = mapped_column(ForeignKey("languages.id"), nullable=False)

    branch = relationship("Branch")


class HonorCategory(BigIntPrimaryKeyMixin, TimestampMixin, SortOrderMixin, Base):
    __tablename__ = "honor_categories"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    type: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("honor_categories.id"))
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    parent = relationship("HonorCategory", remote_side="HonorCategory.id", back_populates="children")
    children = relationship("HonorCategory", back_populates="parent")
    honors = relationship("Honor", back_populates="category")


class Honor(BigIntPrimaryKeyMixin, TimestampMixin, SortOrderMixin, Base):
    __tablename__ = "honors"

    category_id: Mapped[int | None] = mapped_column(ForeignKey("honor_categories.id"), index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    short_description: Mapped[str | None] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(String(500))
    year: Mapped[int | None] = mapped_column(Integer, index=True)
    issued_by: Mapped[str | None] = mapped_column(String(255))
    display_type: Mapped[str] = mapped_column(String(100), index=True, default="qualification_certificate", nullable=False)
    is_featured: Mapped[bool] = mapped_column(default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("admin_users.id"))
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("admin_users.id"))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    category = relationship("HonorCategory", back_populates="honors")
