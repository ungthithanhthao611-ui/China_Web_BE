from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.content import Banner, ContentBlock, ContentBlockItem, Page, PageSection
from app.models.media import EntityMedia, MediaAsset
from app.models.navigation import Menu, MenuItem
from app.models.news import Post, PostCategory
from app.models.organization import Branch, Contact, Honor, Video
from app.models.projects import Project, ProjectCategory
from app.models.taxonomy import Language, SiteSetting
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
    PostRead,
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


def list_posts(
    db: Session,
    language_code: str,
    category_slug: str | None,
    skip: int,
    limit: int,
) -> dict[str, Any]:
    language = get_language(db, language_code)
    base_query = (
        select(Post)
        .options(selectinload(Post.image), selectinload(Post.category))
        .where(Post.language_id == language.id, Post.status == "published")
    )
    if category_slug:
        base_query = base_query.join(PostCategory).where(PostCategory.slug == category_slug)

    ordered_query = base_query.order_by(Post.published_at.desc().nullslast(), Post.id.desc())
    total = len(db.scalars(base_query).all())
    items = db.scalars(ordered_query.offset(skip).limit(limit)).all()

    payload = []
    for item in items:
        data = _serialize(PostRead, item)
        data["image"] = _serialize_media(item.image)
        data["category"] = (
            {"id": item.category.id, "name": item.category.name, "slug": item.category.slug}
            if item.category
            else None
        )
        payload.append(data)
    return {"items": payload, "pagination": {"skip": skip, "limit": limit, "total": total}}


def get_post_detail(db: Session, slug: str, language_code: str) -> dict[str, Any]:
    language = get_language(db, language_code)
    post = db.scalar(
        select(Post)
        .options(selectinload(Post.image), selectinload(Post.category))
        .where(Post.slug == slug, Post.language_id == language.id, Post.status == "published")
    )
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found.")

    data = _serialize(PostRead, post)
    data["image"] = _serialize_media(post.image)
    data["category"] = (
        {"id": post.category.id, "name": post.category.name, "slug": post.category.slug}
        if post.category
        else None
    )
    data["gallery"] = _entity_gallery(db, "post", post.id)
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


def list_honors(db: Session, language_code: str, award_year: int | None) -> list[dict[str, Any]]:
    language = get_language(db, language_code)
    query = (
        select(Honor)
        .options(selectinload(Honor.image), selectinload(Honor.project))
        .where(Honor.language_id == language.id)
        .order_by(Honor.sort_order, Honor.award_year.desc().nullslast(), Honor.id.desc())
    )
    if award_year:
        query = query.where(Honor.award_year == award_year)

    honors = db.scalars(query).all()
    payload = []
    for honor in honors:
        payload.append(
            {
                **_serialize(HonorRead, honor),
                "image": _serialize_media(honor.image),
                "project": (
                    {"id": honor.project.id, "title": honor.project.title, "slug": honor.project.slug}
                    if honor.project
                    else None
                ),
            }
        )
    return payload


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
