from sqlalchemy import Boolean, ForeignKey, String, Text, UniqueConstraint
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

    items: Mapped[list["ProjectCategoryItem"]] = relationship(
        "ProjectCategoryItem",
        back_populates="category",
        cascade="all, delete-orphan",
    )


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
    legacy_detail_id: Mapped[str | None] = mapped_column(String(32), index=True)
    legacy_detail_href: Mapped[str | None] = mapped_column(String(500))
    language_id: Mapped[int] = mapped_column(ForeignKey("languages.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="published", index=True, nullable=False)
    meta_title: Mapped[str | None] = mapped_column(String(255))
    meta_description: Mapped[str | None] = mapped_column(String(500))

    category = relationship("ProjectCategory")
    image = relationship("MediaAsset", foreign_keys=[image_id])
    hero_image = relationship("MediaAsset", foreign_keys=[hero_image_id])
    category_items: Mapped[list["ProjectCategoryItem"]] = relationship(
        "ProjectCategoryItem",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    project_products: Mapped[list["ProjectProduct"]] = relationship(
        "ProjectProduct",
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="ProjectProduct.sort_order",
    )


class ProjectProduct(BigIntPrimaryKeyMixin, TimestampMixin, SortOrderMixin, Base):
    __tablename__ = "project_products"
    __table_args__ = (
        UniqueConstraint("project_id", "product_id", name="uq_project_products_project_product"),
    )

    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)

    project = relationship("Project", back_populates="project_products")
    product = relationship("Product", back_populates="project_products")


class ProjectCategoryItem(BigIntPrimaryKeyMixin, TimestampMixin, SortOrderMixin, Base):
    __tablename__ = "project_category_items"
    __table_args__ = (
        UniqueConstraint("category_id", "project_id", name="uq_project_category_items_category_project"),
        UniqueConstraint("category_id", "anchor", name="uq_project_category_items_category_anchor"),
    )

    category_id: Mapped[int] = mapped_column(ForeignKey("project_categories.id"), index=True, nullable=False)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True, nullable=False)
    anchor: Mapped[str] = mapped_column(String(100), nullable=False)
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    layout_variant: Mapped[str] = mapped_column(String(50), default="feature", nullable=False)

    category = relationship("ProjectCategory", back_populates="items")
    project = relationship("Project", back_populates="category_items")
