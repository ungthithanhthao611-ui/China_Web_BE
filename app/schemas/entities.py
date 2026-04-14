from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class LanguageCreate(BaseModel):
    code: str
    name: str
    is_default: bool = False
    status: str = "active"


class LanguageUpdate(BaseModel):
    code: str | None = None
    name: str | None = None
    is_default: bool | None = None
    status: str | None = None


class LanguageRead(ORMModel):
    id: int
    code: str
    name: str
    is_default: bool
    status: str


class TranslationCreate(BaseModel):
    language_id: int
    entity_type: str
    entity_id: int
    field_name: str
    translated_text: str


class TranslationUpdate(BaseModel):
    language_id: int | None = None
    entity_type: str | None = None
    entity_id: int | None = None
    field_name: str | None = None
    translated_text: str | None = None


class TranslationRead(ORMModel):
    id: int
    language_id: int
    entity_type: str
    entity_id: int
    field_name: str
    translated_text: str
    created_at: datetime
    updated_at: datetime


class SiteSettingCreate(BaseModel):
    config_key: str
    config_value: str | None = None
    language_id: int | None = None
    group_name: str | None = None
    description: str | None = None


class SiteSettingUpdate(BaseModel):
    config_key: str | None = None
    config_value: str | None = None
    language_id: int | None = None
    group_name: str | None = None
    description: str | None = None


class SiteSettingRead(ORMModel):
    id: int
    config_key: str
    config_value: str | None
    language_id: int | None
    group_name: str | None
    description: str | None
    updated_at: datetime | None


class MediaAssetCreate(BaseModel):
    uuid: str
    file_name: str | None = None
    url: str
    storage_path: str | None = None
    asset_type: str
    mime_type: str | None = None
    width: int | None = None
    height: int | None = None
    size: int | None = None
    alt_text: str | None = None
    title: str | None = None
    status: str = "active"


class MediaAssetUpdate(BaseModel):
    uuid: str | None = None
    file_name: str | None = None
    url: str | None = None
    storage_path: str | None = None
    asset_type: str | None = None
    mime_type: str | None = None
    width: int | None = None
    height: int | None = None
    size: int | None = None
    alt_text: str | None = None
    title: str | None = None
    status: str | None = None


class MediaAssetRead(ORMModel):
    id: int
    uuid: str
    file_name: str | None
    url: str
    storage_path: str | None
    asset_type: str
    mime_type: str | None
    width: int | None
    height: int | None
    size: int | None
    alt_text: str | None
    title: str | None
    status: str
    created_at: datetime
    updated_at: datetime


class EntityMediaCreate(BaseModel):
    entity_type: str
    entity_id: int
    media_id: int
    group_name: str = "default"
    sort_order: int = 0
    caption: str | None = None


class EntityMediaUpdate(BaseModel):
    entity_type: str | None = None
    entity_id: int | None = None
    media_id: int | None = None
    group_name: str | None = None
    sort_order: int | None = None
    caption: str | None = None


class EntityMediaRead(ORMModel):
    id: int
    entity_type: str
    entity_id: int
    media_id: int
    group_name: str
    sort_order: int
    caption: str | None
    created_at: datetime
    updated_at: datetime


class MenuCreate(BaseModel):
    name: str
    location: str | None = None
    language_id: int
    is_active: bool = True


class MenuUpdate(BaseModel):
    name: str | None = None
    location: str | None = None
    language_id: int | None = None
    is_active: bool | None = None


class MenuRead(ORMModel):
    id: int
    name: str
    location: str | None
    language_id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


class MenuItemCreate(BaseModel):
    menu_id: int
    parent_id: int | None = None
    title: str
    url: str
    target: str | None = None
    item_type: str | None = None
    page_id: int | None = None
    anchor: str | None = None
    sort_order: int = 0


class MenuItemUpdate(BaseModel):
    menu_id: int | None = None
    parent_id: int | None = None
    title: str | None = None
    url: str | None = None
    target: str | None = None
    item_type: str | None = None
    page_id: int | None = None
    anchor: str | None = None
    sort_order: int | None = None


class MenuItemRead(ORMModel):
    id: int
    menu_id: int
    parent_id: int | None
    title: str
    url: str
    target: str | None
    item_type: str | None
    page_id: int | None
    anchor: str | None
    sort_order: int


class PageCreate(BaseModel):
    slug: str
    title: str | None = None
    summary: str | None = None
    body: str | None = None
    page_type: str | None = None
    language_id: int
    parent_id: int | None = None
    status: str = "published"
    meta_title: str | None = None
    meta_description: str | None = None
    sort_order: int = 0


class PageUpdate(BaseModel):
    slug: str | None = None
    title: str | None = None
    summary: str | None = None
    body: str | None = None
    page_type: str | None = None
    language_id: int | None = None
    parent_id: int | None = None
    status: str | None = None
    meta_title: str | None = None
    meta_description: str | None = None
    sort_order: int | None = None


class PageRead(ORMModel):
    id: int
    slug: str
    title: str | None
    summary: str | None
    body: str | None
    page_type: str | None
    language_id: int
    parent_id: int | None
    status: str
    meta_title: str | None
    meta_description: str | None
    sort_order: int
    created_at: datetime
    updated_at: datetime


class PageSectionCreate(BaseModel):
    page_id: int
    anchor: str | None = None
    title: str | None = None
    content: str | None = None
    image_id: int | None = None
    section_type: str | None = None
    sort_order: int = 0


class PageSectionUpdate(BaseModel):
    page_id: int | None = None
    anchor: str | None = None
    title: str | None = None
    content: str | None = None
    image_id: int | None = None
    section_type: str | None = None
    sort_order: int | None = None


class PageSectionRead(ORMModel):
    id: int
    page_id: int
    anchor: str | None
    title: str | None
    content: str | None
    image_id: int | None
    section_type: str | None
    sort_order: int
    created_at: datetime
    updated_at: datetime


class BannerCreate(BaseModel):
    title: str | None = None
    subtitle: str | None = None
    body: str | None = None
    image_id: int | None = None
    link: str | None = None
    button_text: str | None = None
    banner_type: str | None = None
    language_id: int
    sort_order: int = 0
    is_active: bool = True


class BannerUpdate(BaseModel):
    title: str | None = None
    subtitle: str | None = None
    body: str | None = None
    image_id: int | None = None
    link: str | None = None
    button_text: str | None = None
    banner_type: str | None = None
    language_id: int | None = None
    sort_order: int | None = None
    is_active: bool | None = None


class BannerRead(ORMModel):
    id: int
    title: str | None
    subtitle: str | None
    body: str | None
    image_id: int | None
    link: str | None
    button_text: str | None
    banner_type: str | None
    language_id: int
    sort_order: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ContentBlockCreate(BaseModel):
    entity_type: str
    entity_id: int
    language_id: int | None = None
    block_key: str
    title: str | None = None
    subtitle: str | None = None
    content: str | None = None
    block_type: str
    sort_order: int = 0


class ContentBlockUpdate(BaseModel):
    entity_type: str | None = None
    entity_id: int | None = None
    language_id: int | None = None
    block_key: str | None = None
    title: str | None = None
    subtitle: str | None = None
    content: str | None = None
    block_type: str | None = None
    sort_order: int | None = None


class ContentBlockRead(ORMModel):
    id: int
    entity_type: str
    entity_id: int
    language_id: int | None
    block_key: str
    title: str | None
    subtitle: str | None
    content: str | None
    block_type: str
    sort_order: int
    created_at: datetime
    updated_at: datetime


class ContentBlockItemCreate(BaseModel):
    block_id: int
    item_key: str | None = None
    title: str | None = None
    subtitle: str | None = None
    content: str | None = None
    link: str | None = None
    image_id: int | None = None
    metadata_json: dict[str, Any] | None = None
    sort_order: int = 0


class ContentBlockItemUpdate(BaseModel):
    block_id: int | None = None
    item_key: str | None = None
    title: str | None = None
    subtitle: str | None = None
    content: str | None = None
    link: str | None = None
    image_id: int | None = None
    metadata_json: dict[str, Any] | None = None
    sort_order: int | None = None


class ContentBlockItemRead(ORMModel):
    id: int
    block_id: int
    item_key: str | None
    title: str | None
    subtitle: str | None
    content: str | None
    link: str | None
    image_id: int | None
    metadata_json: dict[str, Any] | None
    sort_order: int
    created_at: datetime
    updated_at: datetime


class PostCategoryCreate(BaseModel):
    name: str
    slug: str
    description: str | None = None
    parent_id: int | None = None
    sort_order: int = 0
    status: str = "active"


class PostCategoryUpdate(BaseModel):
    name: str | None = None
    slug: str | None = None
    description: str | None = None
    parent_id: int | None = None
    sort_order: int | None = None
    status: str | None = None


class PostCategoryRead(ORMModel):
    id: int
    name: str
    slug: str
    description: str | None
    parent_id: int | None
    sort_order: int
    status: str
    created_at: datetime
    updated_at: datetime


class PostCreate(BaseModel):
    category_id: int | None = None
    title: str
    slug: str
    summary: str | None = None
    body: str | None = None
    published_at: datetime | None = None
    author: str | None = None
    image_id: int | None = None
    language_id: int
    status: str = "published"
    meta_title: str | None = None
    meta_description: str | None = None


class PostUpdate(BaseModel):
    category_id: int | None = None
    title: str | None = None
    slug: str | None = None
    summary: str | None = None
    body: str | None = None
    published_at: datetime | None = None
    author: str | None = None
    image_id: int | None = None
    language_id: int | None = None
    status: str | None = None
    meta_title: str | None = None
    meta_description: str | None = None


class PostRead(ORMModel):
    id: int
    category_id: int | None
    title: str
    slug: str
    summary: str | None
    body: str | None
    published_at: datetime | None
    author: str | None
    image_id: int | None
    language_id: int
    status: str
    meta_title: str | None
    meta_description: str | None
    created_at: datetime
    updated_at: datetime


class ProjectCategoryCreate(BaseModel):
    name: str
    slug: str
    description: str | None = None
    parent_id: int | None = None
    sort_order: int = 0
    status: str = "active"


class ProjectCategoryUpdate(BaseModel):
    name: str | None = None
    slug: str | None = None
    description: str | None = None
    parent_id: int | None = None
    sort_order: int | None = None
    status: str | None = None


class ProjectCategoryRead(ORMModel):
    id: int
    name: str
    slug: str
    description: str | None
    parent_id: int | None
    sort_order: int
    status: str
    created_at: datetime
    updated_at: datetime


class ProjectCreate(BaseModel):
    category_id: int | None = None
    title: str
    slug: str
    summary: str | None = None
    body: str | None = None
    location: str | None = None
    project_year: int | None = None
    image_id: int | None = None
    hero_image_id: int | None = None
    language_id: int
    status: str = "published"
    meta_title: str | None = None
    meta_description: str | None = None


class ProjectUpdate(BaseModel):
    category_id: int | None = None
    title: str | None = None
    slug: str | None = None
    summary: str | None = None
    body: str | None = None
    location: str | None = None
    project_year: int | None = None
    image_id: int | None = None
    hero_image_id: int | None = None
    language_id: int | None = None
    status: str | None = None
    meta_title: str | None = None
    meta_description: str | None = None


class ProjectRead(ORMModel):
    id: int
    category_id: int | None
    title: str
    slug: str
    summary: str | None
    body: str | None
    location: str | None
    project_year: int | None
    image_id: int | None
    hero_image_id: int | None
    language_id: int
    status: str
    meta_title: str | None
    meta_description: str | None
    created_at: datetime
    updated_at: datetime


class VideoCreate(BaseModel):
    title: str
    description: str | None = None
    video_url: str
    thumbnail_id: int | None = None
    language_id: int
    sort_order: int = 0
    status: str = "published"


class VideoUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    video_url: str | None = None
    thumbnail_id: int | None = None
    language_id: int | None = None
    sort_order: int | None = None
    status: str | None = None


class VideoRead(ORMModel):
    id: int
    title: str
    description: str | None
    video_url: str
    thumbnail_id: int | None
    language_id: int
    sort_order: int
    status: str
    created_at: datetime
    updated_at: datetime


class ContactCreate(BaseModel):
    name: str
    contact_type: str | None = None
    address: str | None = None
    phone: str | None = None
    email: EmailStr | None = None
    map_url: str | None = None
    latitude: str | None = None
    longitude: str | None = None
    branch_id: int | None = None
    is_primary: bool = False
    language_id: int


class ContactUpdate(BaseModel):
    name: str | None = None
    contact_type: str | None = None
    address: str | None = None
    phone: str | None = None
    email: EmailStr | None = None
    map_url: str | None = None
    latitude: str | None = None
    longitude: str | None = None
    branch_id: int | None = None
    is_primary: bool | None = None
    language_id: int | None = None


class ContactRead(ORMModel):
    id: int
    name: str
    contact_type: str | None
    address: str | None
    phone: str | None
    email: EmailStr | None
    map_url: str | None
    latitude: str | None
    longitude: str | None
    branch_id: int | None
    is_primary: bool
    language_id: int
    created_at: datetime
    updated_at: datetime


class HonorCreate(BaseModel):
    title: str
    description: str | None = None
    award_year: int | None = None
    award_category: str | None = None
    project_id: int | None = None
    image_id: int | None = None
    issuer: str | None = None
    language_id: int
    sort_order: int = 0


class HonorUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    award_year: int | None = None
    award_category: str | None = None
    project_id: int | None = None
    image_id: int | None = None
    issuer: str | None = None
    language_id: int | None = None
    sort_order: int | None = None


class HonorRead(ORMModel):
    id: int
    title: str
    description: str | None
    award_year: int | None
    award_category: str | None
    project_id: int | None
    image_id: int | None
    issuer: str | None
    language_id: int
    sort_order: int
    created_at: datetime
    updated_at: datetime


class BranchCreate(BaseModel):
    name: str
    slug: str
    branch_type: str | None = None
    address: str | None = None
    city: str | None = None
    region: str | None = None
    phone: str | None = None
    email: EmailStr | None = None
    map_url: str | None = None
    parent_id: int | None = None
    is_active: bool = True
    language_id: int
    summary: str | None = None
    body: str | None = None
    image_id: int | None = None
    hero_image_id: int | None = None
    meta_title: str | None = None
    meta_description: str | None = None


class BranchUpdate(BaseModel):
    name: str | None = None
    slug: str | None = None
    branch_type: str | None = None
    address: str | None = None
    city: str | None = None
    region: str | None = None
    phone: str | None = None
    email: EmailStr | None = None
    map_url: str | None = None
    parent_id: int | None = None
    is_active: bool | None = None
    language_id: int | None = None
    summary: str | None = None
    body: str | None = None
    image_id: int | None = None
    hero_image_id: int | None = None
    meta_title: str | None = None
    meta_description: str | None = None


class BranchRead(ORMModel):
    id: int
    name: str
    slug: str
    branch_type: str | None
    address: str | None
    city: str | None
    region: str | None
    phone: str | None
    email: EmailStr | None
    map_url: str | None
    parent_id: int | None
    is_active: bool
    language_id: int
    summary: str | None
    body: str | None
    image_id: int | None
    hero_image_id: int | None
    meta_title: str | None
    meta_description: str | None
    created_at: datetime
    updated_at: datetime


class InquirySubmissionCreate(BaseModel):
    full_name: str
    email: EmailStr
    phone: str | None = None
    company: str | None = None
    subject: str | None = None
    message: str
    source_page: str | None = None
    status: str = "new"


class InquirySubmissionUpdate(BaseModel):
    full_name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    company: str | None = None
    subject: str | None = None
    message: str | None = None
    source_page: str | None = None
    status: str | None = None


class InquirySubmissionRead(ORMModel):
    id: int
    full_name: str
    email: EmailStr
    phone: str | None
    company: str | None
    subject: str | None
    message: str
    source_page: str | None
    status: str
    created_at: datetime
    updated_at: datetime
