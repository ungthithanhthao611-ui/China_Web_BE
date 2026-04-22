from sqlalchemy import ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import BigIntPrimaryKeyMixin, SortOrderMixin, TimestampMixin


class Page(BigIntPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "pages"

    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    title: Mapped[str | None] = mapped_column(String(255))
    summary: Mapped[str | None] = mapped_column(Text)
    body: Mapped[str | None] = mapped_column(Text)
    page_type: Mapped[str | None] = mapped_column(String(100), index=True)
    language_id: Mapped[int] = mapped_column(ForeignKey("languages.id"), nullable=False)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("pages.id"))
    status: Mapped[str] = mapped_column(String(50), default="published", index=True, nullable=False)
    meta_title: Mapped[str | None] = mapped_column(String(255))
    meta_description: Mapped[str | None] = mapped_column(String(500))
    sort_order: Mapped[int] = mapped_column(default=0, index=True, nullable=False)

    sections: Mapped[list["PageSection"]] = relationship(back_populates="page", cascade="all, delete-orphan")


class PageSection(BigIntPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "page_sections"

    page_id: Mapped[int] = mapped_column(ForeignKey("pages.id"), nullable=False)
    anchor: Mapped[str | None] = mapped_column(String(100), index=True)
    title: Mapped[str | None] = mapped_column(String(255))
    content: Mapped[str | None] = mapped_column(Text)
    image_id: Mapped[int | None] = mapped_column(ForeignKey("media_assets.id"))
    section_type: Mapped[str | None] = mapped_column(String(100), index=True)
    sort_order: Mapped[int] = mapped_column(default=0, index=True, nullable=False)

    page: Mapped["Page"] = relationship(back_populates="sections")
    image = relationship("MediaAsset")


class Banner(BigIntPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "banners"

    title: Mapped[str | None] = mapped_column(String(255))
    subtitle: Mapped[str | None] = mapped_column(String(500))
    body: Mapped[str | None] = mapped_column(Text)
    image_id: Mapped[int | None] = mapped_column(ForeignKey("media_assets.id"))
    link: Mapped[str | None] = mapped_column(String(500))
    button_text: Mapped[str | None] = mapped_column(String(100))
    banner_type: Mapped[str | None] = mapped_column(String(100), index=True)
    placement: Mapped[str | None] = mapped_column(String(100), index=True, default="home")
    focus_x: Mapped[float] = mapped_column(default=50.0, nullable=False)
    focus_y: Mapped[float] = mapped_column(default=50.0, nullable=False)
    language_id: Mapped[int | None] = mapped_column(ForeignKey("languages.id"), nullable=True)
    sort_order: Mapped[int] = mapped_column(default=0, index=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    image = relationship("MediaAsset")


class ContentBlock(BigIntPrimaryKeyMixin, TimestampMixin, SortOrderMixin, Base):
    __tablename__ = "content_blocks"

    entity_type: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    entity_id: Mapped[int] = mapped_column(index=True, nullable=False)
    language_id: Mapped[int | None] = mapped_column(ForeignKey("languages.id"))
    block_key: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    title: Mapped[str | None] = mapped_column(String(255))
    subtitle: Mapped[str | None] = mapped_column(String(500))
    content: Mapped[str | None] = mapped_column(Text)
    block_type: Mapped[str] = mapped_column(String(100), index=True, nullable=False)

    items: Mapped[list["ContentBlockItem"]] = relationship(
        back_populates="block",
        cascade="all, delete-orphan",
        order_by="ContentBlockItem.sort_order",
    )


class ContentBlockItem(BigIntPrimaryKeyMixin, TimestampMixin, SortOrderMixin, Base):
    __tablename__ = "content_block_items"

    block_id: Mapped[int] = mapped_column(ForeignKey("content_blocks.id"), nullable=False)
    item_key: Mapped[str | None] = mapped_column(String(100), index=True)
    title: Mapped[str | None] = mapped_column(String(255))
    subtitle: Mapped[str | None] = mapped_column(String(500))
    content: Mapped[str | None] = mapped_column(Text)
    link: Mapped[str | None] = mapped_column(String(500))
    image_id: Mapped[int | None] = mapped_column(ForeignKey("media_assets.id"))
    metadata_json: Mapped[dict | None] = mapped_column(JSON, default=None)

    block: Mapped["ContentBlock"] = relationship(back_populates="items")
    image = relationship("MediaAsset")
