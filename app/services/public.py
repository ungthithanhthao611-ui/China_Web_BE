from collections.abc import Iterable
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.content import Banner, ContentBlock, ContentBlockItem, Page, PageSection
from app.models.media import EntityMedia, MediaAsset
from app.models.navigation import Menu, MenuItem
from app.models.organization import Branch, Contact, Video
from app.models.products import ContactInquiry, Product, ProductCategory, ProductImage
from app.models.projects import Project, ProjectCategory, ProjectCategoryItem
from app.schemas.products import InquiryCreate, ProductCategoryRead, ProductListItemRead, ProductRead
from app.schemas.projects import ProjectCasePageRead
from app.models.taxonomy import Language, SiteSetting
from app.services.honors import list_public_honors
from app.schemas.entities import (
    BannerRead,
    BranchRead,
    ContactRead,
    ContentBlockItemRead,
    ContentBlockRead,
    LanguageRead,
    MediaAssetRead,
    PageRead,
    PageSectionRead,
    ProjectRead,
    SiteSettingRead,
    VideoRead,
)


def _serialize(schema: type, record: Any) -> dict[str, Any]:
    return schema.model_validate(record).model_dump(mode="json")


def get_language(db: Session, language_code: str) -> Language:
    language = db.scalar(select(Language).where(Language.code == language_code, Language.status == "active"))
    if language:
        return language

    language = db.scalar(select(Language).where(Language.is_default.is_(True)))
    if language:
        return language

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active language configured.")


def _get_default_language(db: Session) -> Language | None:
    default_language = db.scalar(select(Language).where(Language.is_default.is_(True), Language.status == "active"))
    if default_language:
        return default_language
    return db.scalar(select(Language).where(Language.status == "active").order_by(Language.id.asc()))


def _serialize_media(record: MediaAsset | None) -> dict[str, Any] | None:
    if not record:
        return None
    return _serialize(MediaAssetRead, record)


def _entity_gallery(db: Session, entity_type: str, entity_id: int) -> list[dict[str, Any]]:
    items = db.scalars(
        select(EntityMedia)
        .options(selectinload(EntityMedia.media))
        .where(EntityMedia.entity_type == entity_type, EntityMedia.entity_id == entity_id)
        .order_by(EntityMedia.group_name, EntityMedia.sort_order, EntityMedia.id)
    ).all()
    return [
        {
            "id": item.id,
            "group_name": item.group_name,
            "sort_order": item.sort_order,
            "caption": item.caption,
            "media": _serialize_media(item.media),
        }
        for item in items
    ]


def _entity_media_groups(
    db: Session,
    entity_types: str | Iterable[str],
    entity_ids: list[int],
) -> dict[int, dict[str, list[dict[str, Any]]]]:
    if not entity_ids:
        return {}

    normalized_entity_types = [entity_types] if isinstance(entity_types, str) else list(entity_types)
    items = db.scalars(
        select(EntityMedia)
        .options(selectinload(EntityMedia.media))
        .where(
            EntityMedia.entity_type.in_(normalized_entity_types),
            EntityMedia.entity_id.in_(entity_ids),
        )
        .order_by(EntityMedia.entity_id, EntityMedia.group_name, EntityMedia.sort_order, EntityMedia.id)
    ).all()

    grouped: dict[int, dict[str, list[dict[str, Any]]]] = {}
    for item in items:
        group_bucket = grouped.setdefault(item.entity_id, {})
        group_bucket.setdefault(item.group_name, []).append(
            {
                "id": item.id,
                "group_name": item.group_name,
                "sort_order": item.sort_order,
                "caption": item.caption,
                "media": _serialize_media(item.media),
            }
        )
    return grouped


def _media_group_urls(
    media_groups: dict[str, list[dict[str, Any]]] | None,
    group_name: str,
) -> list[str]:
    if not media_groups:
        return []
    return [
        item.get("media", {}).get("url")
        for item in media_groups.get(group_name, [])
        if item.get("media", {}).get("url")
    ]


def _content_blocks(db: Session, entity_type: str, entity_id: int, language_id: int) -> list[dict[str, Any]]:
    blocks = db.scalars(
        select(ContentBlock)
        .options(selectinload(ContentBlock.items).selectinload(ContentBlockItem.image))
        .where(
            ContentBlock.entity_type == entity_type,
            ContentBlock.entity_id == entity_id,
            or_(ContentBlock.language_id == language_id, ContentBlock.language_id.is_(None)),
        )
        .order_by(ContentBlock.sort_order, ContentBlock.id)
    ).all()

    payload: list[dict[str, Any]] = []
    for block in blocks:
        block_data = _serialize(ContentBlockRead, block)
        block_data["items"] = []
        for item in block.items:
            item_data = _serialize(ContentBlockItemRead, item)
            item_data["image"] = _serialize_media(item.image)
            block_data["items"].append(item_data)
        payload.append(block_data)
    return payload


def _build_menu_tree(items: list[MenuItem]) -> list[dict[str, Any]]:
    nodes: dict[int, dict[str, Any]] = {}
    roots: list[dict[str, Any]] = []

    sorted_items = sorted(items, key=lambda item: (item.sort_order, item.id))
    for item in sorted_items:
        nodes[item.id] = {
            "id": item.id,
            "title": item.title,
            "url": item.url,
            "target": item.target,
            "item_type": item.item_type,
            "page_id": item.page_id,
            "anchor": item.anchor,
            "sort_order": item.sort_order,
            "children": [],
        }

    for item in sorted_items:
        node = nodes[item.id]
        if item.parent_id and item.parent_id in nodes:
            nodes[item.parent_id]["children"].append(node)
        else:
            roots.append(node)
    return roots


def get_bootstrap_payload(db: Session, language_code: str) -> dict[str, Any]:
    language = get_language(db, language_code)
    menus = db.scalars(
        select(Menu)
        .options(selectinload(Menu.items))
        .where(Menu.language_id == language.id, Menu.is_active.is_(True))
        .order_by(Menu.id)
    ).all()
    settings_rows = db.scalars(
        select(SiteSetting).where(or_(SiteSetting.language_id == language.id, SiteSetting.language_id.is_(None)))
    ).all()
    banners = list_banners(db=db, language_code=language.code, banner_type="hero")

    menu_payload = {}
    for menu in menus:
        menu_payload[menu.location or menu.name] = {
            "id": menu.id,
            "name": menu.name,
            "items": _build_menu_tree(menu.items),
        }

    return {
        "language": _serialize(LanguageRead, language),
        "menus": menu_payload,
        "settings": [_serialize(SiteSettingRead, row) for row in settings_rows],
        "hero_banners": banners,
    }


def list_banners(db: Session, language_code: str, banner_type: str | None) -> list[dict[str, Any]]:
    language = get_language(db, language_code)
    query = (
        select(Banner)
        .options(selectinload(Banner.image))
        .where(Banner.language_id == language.id, Banner.is_active.is_(True))
        .order_by(Banner.sort_order, Banner.id)
    )
    if banner_type:
        query = query.where(Banner.banner_type == banner_type)

    banners = db.scalars(query).all()
    payload = []
    for banner in banners:
        data = _serialize(BannerRead, banner)
        data["image"] = _serialize_media(banner.image)
        payload.append(data)
    return payload


def get_page_detail(db: Session, slug: str, language_code: str) -> dict[str, Any]:
    language = get_language(db, language_code)
    page = db.scalar(
        select(Page)
        .options(selectinload(Page.sections).selectinload(PageSection.image))
        .where(Page.slug == slug, Page.language_id == language.id, Page.status == "published")
    )
    if not page:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page not found.")

    data = _serialize(PageRead, page)
    data["sections"] = []
    for section in sorted(page.sections, key=lambda row: (row.sort_order, row.id)):
        section_data = _serialize(PageSectionRead, section)
        section_data["image"] = _serialize_media(section.image)
        data["sections"].append(section_data)
    data["blocks"] = _content_blocks(db, "page", page.id, language.id)
    data["gallery"] = _entity_gallery(db, "page", page.id)
    return data




def list_projects(
    db: Session,
    language_code: str,
    category_slug: str | None,
    year: int | None,
    skip: int,
    limit: int,
) -> dict[str, Any]:
    language = get_language(db, language_code)
    base_query = (
        select(Project)
        .options(selectinload(Project.image), selectinload(Project.hero_image), selectinload(Project.category))
        .where(Project.language_id == language.id, Project.status == "published")
    )
    if category_slug:
        base_query = base_query.join(ProjectCategory).where(ProjectCategory.slug == category_slug)
    if year:
        base_query = base_query.where(Project.project_year == year)

    ordered_query = base_query.order_by(Project.project_year.desc().nullslast(), Project.id.desc())
    total = len(db.scalars(base_query).all())
    items = db.scalars(ordered_query.offset(skip).limit(limit)).all()

    payload = []
    for item in items:
        data = _serialize(ProjectRead, item)
        data["image"] = _serialize_media(item.image)
        data["hero_image"] = _serialize_media(item.hero_image)
        data["category"] = (
            {"id": item.category.id, "name": item.category.name, "slug": item.category.slug}
            if item.category
            else None
        )
        payload.append(data)
    return {"items": payload, "pagination": {"skip": skip, "limit": limit, "total": total}}


def get_project_detail(db: Session, slug: str, language_code: str) -> dict[str, Any]:
    language = get_language(db, language_code)
    project = db.scalar(
        select(Project)
        .options(selectinload(Project.image), selectinload(Project.hero_image), selectinload(Project.category))
        .where(Project.slug == slug, Project.language_id == language.id, Project.status == "published")
    )
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")

    data = _serialize(ProjectRead, project)
    data["image"] = _serialize_media(project.image)
    data["hero_image"] = _serialize_media(project.hero_image)
    data["category"] = (
        {"id": project.category.id, "name": project.category.name, "slug": project.category.slug}
        if project.category
        else None
    )
    data["blocks"] = _content_blocks(db, "project", project.id, language.id)
    data["gallery"] = _entity_gallery(db, "project", project.id)
    return data


def get_project_case_page(
    db: Session,
    language_code: str,
    category_id: int | None,
) -> dict[str, Any]:
    language = get_language(db, language_code)
    categories = db.scalars(
        select(ProjectCategory)
        .where(ProjectCategory.status == "active")
        .order_by(ProjectCategory.sort_order, ProjectCategory.id)
    ).all()
    if not categories:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project case categories not found.")

    category_ids = [row.id for row in categories]
    category_media_groups = _entity_media_groups(
        db=db,
        entity_types=["project_category", "project_categories"],
        entity_ids=category_ids,
    )

    category_items = db.scalars(
        select(ProjectCategoryItem)
        .join(Project, Project.id == ProjectCategoryItem.project_id)
        .options(
            selectinload(ProjectCategoryItem.project).selectinload(Project.image),
            selectinload(ProjectCategoryItem.project).selectinload(Project.hero_image),
        )
        .where(
            ProjectCategoryItem.category_id.in_(category_ids),
            Project.status == "published",
            Project.language_id == language.id,
        )
        .order_by(ProjectCategoryItem.category_id, ProjectCategoryItem.sort_order, ProjectCategoryItem.id)
    ).all()

    by_category: dict[int, list[ProjectCategoryItem]] = {row.id: [] for row in categories}
    project_ids: list[int] = []
    for item in category_items:
        by_category.setdefault(item.category_id, []).append(item)
        if item.project_id not in project_ids:
            project_ids.append(item.project_id)

    project_media_groups = _entity_media_groups(
        db=db,
        entity_types="project",
        entity_ids=project_ids,
    )

    def serialize_case(item: ProjectCategoryItem) -> dict[str, Any]:
        project = item.project
        media_groups = project_media_groups.get(project.id, {})
        left_gallery = _media_group_urls(media_groups, "left_gallery")
        right_gallery = _media_group_urls(media_groups, "right_gallery")

        if not left_gallery:
            if project.image and project.image.url:
                left_gallery = [project.image.url]
            elif project.hero_image and project.hero_image.url:
                left_gallery = [project.hero_image.url]

        if not right_gallery:
            if project.hero_image and project.hero_image.url:
                right_gallery = [project.hero_image.url]
            elif left_gallery:
                right_gallery = [left_gallery[0]]

        return {
            "anchor": item.anchor,
            "title": project.title,
            "summary": project.summary or "",
            "detailHref": f"/project/{project.slug}",
            "legacyDetailHref": project.legacy_detail_href,
            "leftGallery": left_gallery,
            "rightGallery": right_gallery,
            "layoutVariant": item.layout_variant or ("feature" if item.is_featured else "standard"),
        }

    category_cases: dict[int, list[dict[str, Any]]] = {}
    for category in categories:
        category_cases[category.id] = [serialize_case(item) for item in by_category.get(category.id, [])]

    selected_category: ProjectCategory | None = None
    if category_id is not None:
        selected_category = next((row for row in categories if row.id == category_id), None)
        if not selected_category:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project case category not found.")

    if selected_category is None:
        selected_category = next((row for row in categories if category_cases.get(row.id)), categories[0])

    categories_payload = [
        {
            "id": str(row.id),
            "name": row.name,
            "slug": row.slug,
        }
        for row in categories
    ]

    hero_slides = []
    for row in categories:
        media_groups = category_media_groups.get(row.id, {})
        desktop_images = _media_group_urls(media_groups, "hero_desktop")
        mobile_images = _media_group_urls(media_groups, "hero_mobile")

        category_case_items = category_cases.get(row.id, [])
        fallback_case = category_case_items[0] if category_case_items else {}
        fallback_left = fallback_case.get("leftGallery") if isinstance(fallback_case, dict) else []
        fallback_right = fallback_case.get("rightGallery") if isinstance(fallback_case, dict) else []

        desktop = desktop_images[0] if desktop_images else (fallback_left[0] if fallback_left else None)
        mobile = mobile_images[0] if mobile_images else (fallback_right[0] if fallback_right else desktop)

        hero_slides.append(
            {
                "categoryId": str(row.id),
                "title": row.name,
                "desktopImage": desktop,
                "mobileImage": mobile,
                "summary": row.description or "",
            }
        )

    payload = {
        "currentCategory": {
            "id": str(selected_category.id),
            "name": selected_category.name,
            "slug": selected_category.slug,
        },
        "categories": categories_payload,
        "heroSlides": hero_slides,
        "cases": category_cases.get(selected_category.id, []),
    }
    return ProjectCasePageRead.model_validate(payload).model_dump(mode="json")


def list_honors(db: Session, language_code: str, award_year: int | None) -> dict[str, Any]:
    # language_code is kept for backward-compatible API shape.
    _ = language_code
    return list_public_honors(db=db, year=award_year)


def list_branches(db: Session, language_code: str, branch_type: str | None) -> list[dict[str, Any]]:
    language = get_language(db, language_code)
    query = (
        select(Branch)
        .options(selectinload(Branch.image), selectinload(Branch.hero_image))
        .where(Branch.language_id == language.id, Branch.is_active.is_(True))
        .order_by(Branch.id.desc())
    )
    if branch_type:
        query = query.where(Branch.branch_type == branch_type)

    branches = db.scalars(query).all()
    payload = []
    for branch in branches:
        data = _serialize(BranchRead, branch)
        data["image"] = _serialize_media(branch.image)
        data["hero_image"] = _serialize_media(branch.hero_image)
        payload.append(data)
    return payload


def get_branch_detail(db: Session, slug: str, language_code: str) -> dict[str, Any]:
    language = get_language(db, language_code)
    branch = db.scalar(
        select(Branch)
        .options(selectinload(Branch.image), selectinload(Branch.hero_image))
        .where(Branch.slug == slug, Branch.language_id == language.id, Branch.is_active.is_(True))
    )
    if not branch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Branch not found.")

    contacts = db.scalars(select(Contact).where(Contact.branch_id == branch.id, Contact.language_id == language.id)).all()
    data = _serialize(BranchRead, branch)
    data["image"] = _serialize_media(branch.image)
    data["hero_image"] = _serialize_media(branch.hero_image)
    data["contacts"] = [_serialize(ContactRead, contact) for contact in contacts]
    data["blocks"] = _content_blocks(db, "branch", branch.id, language.id)
    data["gallery"] = _entity_gallery(db, "branch", branch.id)
    return data


def list_contacts(db: Session, language_code: str) -> list[dict[str, Any]]:
    language = get_language(db, language_code)
    contacts = db.scalars(
        select(Contact)
        .where(Contact.language_id == language.id)
        .order_by(Contact.is_primary.desc(), Contact.id.desc())
    ).all()
    return [_serialize(ContactRead, contact) for contact in contacts]


def list_videos(db: Session, language_code: str) -> list[dict[str, Any]]:
    language = get_language(db, language_code)
    videos = db.scalars(
        select(Video)
        .options(selectinload(Video.thumbnail))
        .where(Video.language_id == language.id, Video.status == "published")
        .order_by(Video.sort_order, Video.id.desc())
    ).all()
    payload = []
    for video in videos:
        data = _serialize(VideoRead, video)
        data["thumbnail"] = _serialize_media(video.thumbnail)
        payload.append(data)
    return payload


# ─── Products ────────────────────────────────────────────────────────────────

def list_product_categories(db: Session) -> dict[str, Any]:
    """Trả về tất cả danh mục sản phẩm active kèm product_count."""
    categories = db.scalars(
        select(ProductCategory)
        .where(ProductCategory.is_active.is_(True))
        .order_by(ProductCategory.sort_order, ProductCategory.id)
    ).all()

    # Đếm số sản phẩm active trong mỗi danh mục
    counts_rows = db.execute(
        select(Product.category_id, func.count(Product.id).label("cnt"))
        .where(Product.is_active.is_(True), Product.category_id.isnot(None))
        .group_by(Product.category_id)
    ).all()
    counts: dict[int, int] = {row.category_id: row.cnt for row in counts_rows}

    payload = []
    for cat in categories:
        data = ProductCategoryRead.model_validate(cat).model_dump(mode="json")
        data["product_count"] = counts.get(cat.id, 0)
        payload.append(data)

    return {"items": payload, "pagination": {"total": len(payload)}}


def list_products(
    db: Session,
    category_slug: str | None,
    skip: int,
    limit: int,
) -> dict[str, Any]:
    base_query = (
        select(Product)
        .options(selectinload(Product.images), selectinload(Product.category))
        .where(Product.is_active.is_(True))
    )
    if category_slug:
        base_query = base_query.join(ProductCategory).where(ProductCategory.slug == category_slug)

    total = db.scalar(select(func.count()).select_from(base_query.subquery()))
    items = db.scalars(
        base_query.order_by(Product.sort_order, Product.id).offset(skip).limit(limit)
    ).all()

    payload = []
    for product in items:
        data = ProductListItemRead.model_validate(product).model_dump(mode="json")
        data["category_name"] = product.category.name if product.category else None
        data["images"] = [
            {"url": img.url, "alt": img.alt, "sort_order": img.sort_order}
            for img in product.images
        ]
        payload.append(data)

    return {"items": payload, "pagination": {"skip": skip, "limit": limit, "total": total or 0}}


def get_product_detail(db: Session, slug: str) -> dict[str, Any]:
    product = db.scalar(
        select(Product)
        .options(selectinload(Product.images), selectinload(Product.category))
        .where(Product.slug == slug, Product.is_active.is_(True))
    )
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found.")

    data = ProductRead.model_validate(product).model_dump(mode="json")
    data["category_name"] = product.category.name if product.category else None
    data["images"] = [
        {"url": img.url, "alt": img.alt, "sort_order": img.sort_order}
        for img in product.images
    ]

    # Related products cùng category
    related: list[dict[str, Any]] = []
    if product.category_id:
        related_products = db.scalars(
            select(Product)
            .options(selectinload(Product.images))
            .where(
                Product.category_id == product.category_id,
                Product.id != product.id,
                Product.is_active.is_(True),
            )
            .order_by(Product.sort_order, Product.id)
            .limit(4)
        ).all()
        for rel in related_products:
            rel_data = ProductListItemRead.model_validate(rel).model_dump(mode="json")
            rel_data["images"] = [
                {"url": img.url, "alt": img.alt} for img in rel.images
            ]
            related.append(rel_data)

    data["related_products"] = related
    return data


# ─── Contact Inquiry ─────────────────────────────────────────────────────────

def create_inquiry(db: Session, payload: InquiryCreate) -> dict[str, Any]:
    inquiry = ContactInquiry(
        full_name=payload.full_name,
        email=payload.email,
        phone=payload.phone,
        company=payload.company,
        subject=payload.subject,
        message=payload.message,
        source_page=payload.source_page,
        product_id=payload.product_id,
        status="new",
    )
    db.add(inquiry)
    db.commit()
    db.refresh(inquiry)
    return {
        "success": True,
        "id": inquiry.id,
        "message": "Yêu cầu đã được ghi nhận. Chúng tôi sẽ liên hệ trong vòng 24 giờ.",
    }

