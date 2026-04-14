from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import BigIntPrimaryKeyMixin, SortOrderMixin, TimestampMixin


class ProjectCategory(BigIntPrimaryKeyMixin, TimestampMixin, SortOrderMixin, Base):
    __tablename__ = "project_categories"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("project_categories.id"))
    status: Mapped[str] = mapped_column(String(50), default="active", index=True, nullable=False)


class Project(BigIntPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "projects"

    category_id: Mapped[int | None] = mapped_column(ForeignKey("project_categories.id"))
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    body: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(String(255))
    project_year: Mapped[int | None] = mapped_column(index=True)
    image_id: Mapped[int | None] = mapped_column(ForeignKey("media_assets.id"))
    hero_image_id: Mapped[int | None] = mapped_column(ForeignKey("media_assets.id"))
    language_id: Mapped[int] = mapped_column(ForeignKey("languages.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="published", index=True, nullable=False)
    meta_title: Mapped[str | None] = mapped_column(String(255))
    meta_description: Mapped[str | None] = mapped_column(String(500))

    category = relationship("ProjectCategory")
    image = relationship("MediaAsset", foreign_keys=[image_id])
    hero_image = relationship("MediaAsset", foreign_keys=[hero_image_id])
