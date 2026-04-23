from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import BigIntPrimaryKeyMixin, SortOrderMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.projects import ProjectProduct


class ProductCategory(BigIntPrimaryKeyMixin, TimestampMixin, SortOrderMixin, Base):
    __tablename__ = "product_categories"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(String(1000))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    products = relationship("Product", back_populates="category", lazy="select")


class Product(BigIntPrimaryKeyMixin, TimestampMixin, SortOrderMixin, Base):
    __tablename__ = "products"

    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("product_categories.id", ondelete="SET NULL"), index=True
    )
    sku: Mapped[str | None] = mapped_column(String(100), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    short_desc: Mapped[str | None] = mapped_column(Text)
    full_desc: Mapped[str | None] = mapped_column(Text)
    size: Mapped[str | None] = mapped_column(String(255))
    material: Mapped[str | None] = mapped_column(String(255))
    color: Mapped[str | None] = mapped_column(Text)
    use_case: Mapped[str | None] = mapped_column(Text)
    video_url: Mapped[str | None] = mapped_column(String(2000))
    catalog_pdf_url: Mapped[str | None] = mapped_column(String(2000))
    image_url: Mapped[str | None] = mapped_column(String(1000))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    category = relationship("ProductCategory", back_populates="products")
    images = relationship(
        "ProductImage", back_populates="product", order_by="ProductImage.sort_order", cascade="all, delete-orphan"
    )
    project_products: Mapped[list["ProjectProduct"]] = relationship(
        "ProjectProduct",
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="ProjectProduct.sort_order",
    )


class ProductImage(BigIntPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "product_images"

    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    url: Mapped[str] = mapped_column(String(2000), nullable=False)
    alt: Mapped[str | None] = mapped_column(String(500))
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    product = relationship("Product", back_populates="images")


class ContactInquiry(BigIntPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "contact_inquiries"

    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    phone: Mapped[str | None] = mapped_column(String(50))
    company: Mapped[str | None] = mapped_column(String(255))
    subject: Mapped[str | None] = mapped_column(String(500))
    message: Mapped[str] = mapped_column(Text, nullable=False)
    source_page: Mapped[str | None] = mapped_column(String(500))
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id", ondelete="SET NULL"), index=True)
    status: Mapped[str] = mapped_column(String(50), default="new", index=True, nullable=False)
    admin_response: Mapped[str | None] = mapped_column(Text)

    product = relationship("Product")
