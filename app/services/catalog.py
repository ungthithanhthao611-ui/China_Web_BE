from dataclasses import dataclass

from app.models.content import Banner, ContentBlock, ContentBlockItem, Page, PageSection
from app.models.media import EntityMedia, MediaAsset
from app.models.navigation import Menu, MenuItem
from app.models.news import Post, PostCategory
from app.models.organization import Branch, Contact, Honor, HonorCategory, Video
from app.models.post_documents import PostDocument  # ensures PostDocument mapper is ready before Post relationship resolves
from app.models.products import ContactInquiry, Product, ProductCategory
from app.models.projects import Project, ProjectCategory, ProjectCategoryItem
from app.models.taxonomy import Language, SiteSetting, Translation
from app.schemas.entities import (
    BannerCreate,
    BannerRead,
    BannerUpdate,
    BranchCreate,
    BranchRead,
    BranchUpdate,
    ContactCreate,
    ContactRead,
    ContactUpdate,
    ContentBlockCreate,
    ContentBlockItemCreate,
    ContentBlockItemRead,
    ContentBlockItemUpdate,
    ContentBlockRead,
    ContentBlockUpdate,
    EntityMediaCreate,
    EntityMediaRead,
    EntityMediaUpdate,
    HonorCreate,
    HonorCategoryCreate,
    HonorCategoryRead,
    HonorCategoryUpdate,
    HonorRead,
    HonorUpdate,
    LanguageCreate,
    LanguageRead,
    LanguageUpdate,
    MediaAssetCreate,
    MediaAssetRead,
    MediaAssetUpdate,
    MenuCreate,
    MenuItemCreate,
    MenuItemRead,
    MenuItemUpdate,
    MenuRead,
    MenuUpdate,
    PageCreate,
    PageRead,
    PageSectionCreate,
    PageSectionRead,
    PageSectionUpdate,
    PageUpdate,
    PostCategoryCreate,
    PostCategoryRead,
    PostCategoryUpdate,
    PostCreate,
    PostRead,
    PostUpdate,
    ProjectCategoryCreate,
    ProjectCategoryItemCreate,
    ProjectCategoryItemRead,
    ProjectCategoryItemUpdate,
    ProjectCategoryRead,
    ProjectCategoryUpdate,
    ProjectCreate,
    ProjectRead,
    ProjectUpdate,
    SiteSettingCreate,
    SiteSettingRead,
    SiteSettingUpdate,
    TranslationCreate,
    TranslationRead,
    TranslationUpdate,
    VideoCreate,
    VideoRead,
    VideoUpdate,
)
from app.schemas.products import (
    InquiryCreate,
    InquiryRead,
    InquiryUpdate,
    ProductCategoryCreate,
    ProductCategoryRead,
    ProductCategoryUpdate,
    ProductCreate,
    ProductRead,
    ProductUpdate,
)


@dataclass(frozen=True)
class EntityRegistration:
    model: type
    read_schema: type
    create_schema: type
    update_schema: type


ENTITY_REGISTRY: dict[str, EntityRegistration] = {
    "languages": EntityRegistration(Language, LanguageRead, LanguageCreate, LanguageUpdate),
    "translations": EntityRegistration(Translation, TranslationRead, TranslationCreate, TranslationUpdate),
    "site_settings": EntityRegistration(SiteSetting, SiteSettingRead, SiteSettingCreate, SiteSettingUpdate),
    "media_assets": EntityRegistration(MediaAsset, MediaAssetRead, MediaAssetCreate, MediaAssetUpdate),
    "entity_media": EntityRegistration(EntityMedia, EntityMediaRead, EntityMediaCreate, EntityMediaUpdate),
    "menus": EntityRegistration(Menu, MenuRead, MenuCreate, MenuUpdate),
    "menu_items": EntityRegistration(MenuItem, MenuItemRead, MenuItemCreate, MenuItemUpdate),
    "pages": EntityRegistration(Page, PageRead, PageCreate, PageUpdate),
    "page_sections": EntityRegistration(PageSection, PageSectionRead, PageSectionCreate, PageSectionUpdate),
    "banners": EntityRegistration(Banner, BannerRead, BannerCreate, BannerUpdate),
    "content_blocks": EntityRegistration(ContentBlock, ContentBlockRead, ContentBlockCreate, ContentBlockUpdate),
    "content_block_items": EntityRegistration(
        ContentBlockItem,
        ContentBlockItemRead,
        ContentBlockItemCreate,
        ContentBlockItemUpdate,
    ),
    "post_categories": EntityRegistration(PostCategory, PostCategoryRead, PostCategoryCreate, PostCategoryUpdate),
    "posts": EntityRegistration(Post, PostRead, PostCreate, PostUpdate),
    "project_categories": EntityRegistration(
        ProjectCategory,
        ProjectCategoryRead,
        ProjectCategoryCreate,
        ProjectCategoryUpdate,
    ),
    "projects": EntityRegistration(Project, ProjectRead, ProjectCreate, ProjectUpdate),
    "project_category_items": EntityRegistration(
        ProjectCategoryItem,
        ProjectCategoryItemRead,
        ProjectCategoryItemCreate,
        ProjectCategoryItemUpdate,
    ),
    "videos": EntityRegistration(Video, VideoRead, VideoCreate, VideoUpdate),
    "contacts": EntityRegistration(Contact, ContactRead, ContactCreate, ContactUpdate),
    "honor_categories": EntityRegistration(
        HonorCategory,
        HonorCategoryRead,
        HonorCategoryCreate,
        HonorCategoryUpdate,
    ),
    "honors": EntityRegistration(Honor, HonorRead, HonorCreate, HonorUpdate),
    "branches": EntityRegistration(Branch, BranchRead, BranchCreate, BranchUpdate),
    # ─── Products ─────────────────────────────────────────────────────────────
    "product_categories": EntityRegistration(
        ProductCategory,
        ProductCategoryRead,
        ProductCategoryCreate,
        ProductCategoryUpdate,
    ),
    "products": EntityRegistration(Product, ProductRead, ProductCreate, ProductUpdate),
    # ─── Inquiries ────────────────────────────────────────────────────────────
    "inquiry_submissions": EntityRegistration(
        ContactInquiry,
        InquiryRead,
        InquiryCreate,
        InquiryUpdate,
    ),
}

