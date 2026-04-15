from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import BigIntPrimaryKeyMixin, SortOrderMixin, TimestampMixin


class Video(BigIntPrimaryKeyMixin, TimestampMixin, SortOrderMixin, Base):
    __tablename__ = "videos"

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    video_url: Mapped[str] = mapped_column(String(500), nullable=False)
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


class Honor(BigIntPrimaryKeyMixin, TimestampMixin, SortOrderMixin, Base):
    __tablename__ = "honors"

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    award_year: Mapped[int | None] = mapped_column(index=True)
    award_category: Mapped[str | None] = mapped_column(String(255))
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"))
    image_id: Mapped[int | None] = mapped_column(ForeignKey("media_assets.id"))
    issuer: Mapped[str | None] = mapped_column(String(255))
    language_id: Mapped[int] = mapped_column(ForeignKey("languages.id"), nullable=False)

    project = relationship("Project")
    image = relationship("MediaAsset")


class InquirySubmission(BigIntPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "inquiry_submissions"

    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    phone: Mapped[str | None] = mapped_column(String(100))
    company: Mapped[str | None] = mapped_column(String(255))
    subject: Mapped[str | None] = mapped_column(String(255))
    message: Mapped[str] = mapped_column(Text, nullable=False)
    source_page: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(50), default="new", index=True, nullable=False)
