from __future__ import annotations
from datetime import datetime

from pydantic import BaseModel, ConfigDict


# ─── ProductImage ────────────────────────────────────────────────────────────

class ProductImageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    url: str
    alt: str | None = None
    sort_order: int = 0


# ─── ProductCategory ─────────────────────────────────────────────────────────

class ProductCategoryNodeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    name_en: str | None = None
    name_zh: str | None = None
    slug: str
    description: str | None = None
    description_en: str | None = None
    description_zh: str | None = None
    parent_id: int | None = None
    image_url: str | None = None
    sort_order: int = 0
    is_active: bool = True
    product_count: int = 0
    direct_product_count: int = 0
    children: list['ProductCategoryNodeRead'] = []


class ProductCategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    name_en: str | None = None
    name_zh: str | None = None
    slug: str
    description: str | None = None
    description_en: str | None = None
    description_zh: str | None = None
    parent_id: int | None = None
    image_url: str | None = None
    sort_order: int = 0
    is_active: bool = True
    product_count: int = 0  # computed, không từ ORM
    direct_product_count: int = 0  # computed, không từ ORM
    children: list[ProductCategoryNodeRead] = []


class ProductCategoryCreate(BaseModel):
    name: str
    name_en: str | None = None
    name_zh: str | None = None
    slug: str
    description: str | None = None
    description_en: str | None = None
    description_zh: str | None = None
    parent_id: int | None = None
    image_url: str | None = None
    sort_order: int = 0
    is_active: bool = True


class ProductCategoryUpdate(BaseModel):
    name: str | None = None
    name_en: str | None = None
    name_zh: str | None = None
    slug: str | None = None
    description: str | None = None
    description_en: str | None = None
    description_zh: str | None = None
    parent_id: int | None = None
    image_url: str | None = None
    sort_order: int | None = None
    is_active: bool | None = None


# ─── Product ─────────────────────────────────────────────────────────────────

class ProductRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category_id: int | None = None
    category_name: str | None = None  # computed
    category_name_en: str | None = None # computed
    category_name_zh: str | None = None # computed
    sku: str | None = None
    name: str
    name_en: str | None = None
    name_zh: str | None = None
    slug: str
    short_desc: str | None = None
    short_desc_en: str | None = None
    short_desc_zh: str | None = None
    full_desc: str | None = None
    full_desc_en: str | None = None
    full_desc_zh: str | None = None
    size: str | None = None
    size_en: str | None = None
    size_zh: str | None = None
    material: str | None = None
    material_en: str | None = None
    material_zh: str | None = None
    color: str | None = None
    color_en: str | None = None
    color_zh: str | None = None
    use_case: str | None = None
    use_case_en: str | None = None
    use_case_zh: str | None = None
    video_url: str | None = None
    catalog_pdf_url: str | None = None
    image_url: str | None = None
    gallery_urls: str | None = None
    is_active: bool = True
    sort_order: int = 0
    images: list[ProductImageRead] = []


class ProductListItemRead(BaseModel):
    """Dùng cho danh sách sản phẩm — nhẹ hơn ProductRead, không bao gồm full_desc."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    category_id: int | None = None
    category_name: str | None = None
    category_name_en: str | None = None
    category_name_zh: str | None = None
    sku: str | None = None
    name: str
    name_en: str | None = None
    name_zh: str | None = None
    slug: str
    short_desc: str | None = None
    short_desc_en: str | None = None
    short_desc_zh: str | None = None
    size: str | None = None
    size_en: str | None = None
    size_zh: str | None = None
    material: str | None = None
    material_en: str | None = None
    material_zh: str | None = None
    image_url: str | None = None
    gallery_urls: str | None = None
    is_active: bool = True
    sort_order: int = 0
    images: list[ProductImageRead] = []


class ProductCreate(BaseModel):
    category_id: int | None = None
    sku: str | None = None
    name: str
    name_en: str | None = None
    name_zh: str | None = None
    slug: str
    short_desc: str | None = None
    short_desc_en: str | None = None
    short_desc_zh: str | None = None
    full_desc: str | None = None
    full_desc_en: str | None = None
    full_desc_zh: str | None = None
    size: str | None = None
    size_en: str | None = None
    size_zh: str | None = None
    material: str | None = None
    material_en: str | None = None
    material_zh: str | None = None
    color: str | None = None
    color_en: str | None = None
    color_zh: str | None = None
    use_case: str | None = None
    use_case_en: str | None = None
    use_case_zh: str | None = None
    video_url: str | None = None
    catalog_pdf_url: str | None = None
    image_url: str | None = None
    gallery_urls: str | None = None
    is_active: bool = True
    sort_order: int = 0


class ProductUpdate(BaseModel):
    category_id: int | None = None
    sku: str | None = None
    name: str | None = None
    name_en: str | None = None
    name_zh: str | None = None
    slug: str | None = None
    short_desc: str | None = None
    short_desc_en: str | None = None
    short_desc_zh: str | None = None
    full_desc: str | None = None
    full_desc_en: str | None = None
    full_desc_zh: str | None = None
    size: str | None = None
    size_en: str | None = None
    size_zh: str | None = None
    material: str | None = None
    material_en: str | None = None
    material_zh: str | None = None
    color: str | None = None
    color_en: str | None = None
    color_zh: str | None = None
    use_case: str | None = None
    use_case_en: str | None = None
    use_case_zh: str | None = None
    video_url: str | None = None
    catalog_pdf_url: str | None = None
    image_url: str | None = None
    gallery_urls: str | None = None
    is_active: bool | None = None
    sort_order: int | None = None


# ─── ContactInquiry ──────────────────────────────────────────────────────────

class InquiryCreate(BaseModel):
    full_name: str
    email: str
    phone: str | None = None
    company: str | None = None
    subject: str | None = None
    message: str
    source_page: str | None = None
    product_id: int | None = None


class InquiryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    email: str
    phone: str | None = None
    company: str | None = None
    subject: str | None = None
    message: str
    source_page: str | None = None
    product_id: int | None = None
    status: str = "new"
    created_at: datetime | None = None
    admin_response: str | None = None


class InquiryUpdate(BaseModel):
    status: str | None = None
    admin_response: str | None = None
