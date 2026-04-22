from datetime import datetime, timezone

from sqlalchemy import delete, inspect, select, text
from sqlalchemy.orm import Session

from app.db.base import *  # noqa: F401,F403
from app.db.session import SessionLocal, engine
from app.core.config import settings
from app.core.security import hash_password
from app.models.admin import AdminUser
from app.models.base import Base
from app.models.content import Banner, ContentBlock, ContentBlockItem, Page, PageSection
from app.models.media import MediaAsset
from app.models.navigation import Menu, MenuItem
from app.models.organization import Contact, Honor, HonorCategory
from app.models.products import ProductCategory
from app.models.taxonomy import Language, SiteSetting
from app.db.seed_about_page import seed_about_page
from app.db.seed_products import seed_products


def initialize_database() -> None:
    Base.metadata.create_all(bind=engine)
    ensure_media_schema()
    ensure_banners_schema()
    ensure_honors_schema()
    ensure_project_case_schema()
    ensure_inquiry_schema()
    with SessionLocal() as session:
        seed_basics(session)


def ensure_inquiry_schema() -> None:
    with engine.begin() as conn:
        inspector = inspect(conn)
        table_names = set(inspector.get_table_names())
        if "contact_inquiries" not in table_names:
            return

        column_names = {column["name"] for column in inspector.get_columns("contact_inquiries")}
        columns_to_add = [
            ("admin_response", "TEXT"),
        ]

        for column_name, column_type in columns_to_add:
            if column_name in column_names:
                continue
            conn.execute(text(f"ALTER TABLE contact_inquiries ADD COLUMN {column_name} {column_type}"))


def ensure_media_schema() -> None:
    with engine.begin() as conn:
        inspector = inspect(conn)
        table_names = set(inspector.get_table_names())
        if "media_assets" not in table_names:
            return

        column_names = {column["name"] for column in inspector.get_columns("media_assets")}
        columns_to_add = [
            ("uploaded_by", "BIGINT"),
        ]

        for column_name, column_type in columns_to_add:
            if column_name in column_names:
                continue
            conn.execute(text(f"ALTER TABLE media_assets ADD COLUMN {column_name} {column_type}"))




def ensure_honors_schema() -> None:
    with engine.begin() as conn:
        inspector = inspect(conn)
        table_names = set(inspector.get_table_names())
        if "honors" not in table_names:
            return

        column_names = {column["name"] for column in inspector.get_columns("honors")}
        columns_to_add = [
            ("category_id", "BIGINT"),
            ("slug", "VARCHAR(255)"),
            ("short_description", "TEXT"),
            ("image_url", "VARCHAR(500)"),
            ("year", "INTEGER"),
            ("issued_by", "VARCHAR(255)"),
            ("display_type", "VARCHAR(100)"),
            ("is_featured", "BOOLEAN"),
            ("is_active", "BOOLEAN"),
            ("created_by", "BIGINT"),
            ("updated_by", "BIGINT"),
            ("deleted_at", "TIMESTAMP WITH TIME ZONE"),
        ]

        for column_name, column_type in columns_to_add:
            if column_name in column_names:
                continue
            conn.execute(text(f"ALTER TABLE honors ADD COLUMN {column_name} {column_type}"))

        refreshed_columns = {column["name"] for column in inspect(conn).get_columns("honors")}

        if "description" in refreshed_columns and "short_description" in refreshed_columns:
            conn.execute(
                text(
                    "UPDATE honors SET short_description = description "
                    "WHERE short_description IS NULL AND description IS NOT NULL"
                )
            )
        if "award_year" in refreshed_columns and "year" in refreshed_columns:
            conn.execute(text("UPDATE honors SET year = award_year WHERE year IS NULL AND award_year IS NOT NULL"))
        if "issuer" in refreshed_columns and "issued_by" in refreshed_columns:
            conn.execute(
                text("UPDATE honors SET issued_by = issuer WHERE issued_by IS NULL AND issuer IS NOT NULL")
            )
        if "image_id" in refreshed_columns and "image_url" in refreshed_columns:
            conn.execute(
                text(
                    "UPDATE honors SET image_url = (SELECT url FROM media_assets WHERE media_assets.id = honors.image_id) "
                    "WHERE image_url IS NULL AND image_id IS NOT NULL"
                )
            )
        if "award_category" in refreshed_columns and "display_type" in refreshed_columns:
            conn.execute(
                text(
                    "UPDATE honors SET display_type = CASE "
                    "WHEN lower(coalesce(award_category, '')) LIKE '%corporate%' THEN 'corporate_honors' "
                    "WHEN lower(coalesce(award_category, '')) LIKE '%project%' THEN 'project_honors' "
                    "ELSE 'qualification_certificate' END "
                    "WHERE display_type IS NULL"
                )
            )

        if "display_type" in refreshed_columns:
            conn.execute(
                text(
                    "UPDATE honors SET display_type = 'qualification_certificate' "
                    "WHERE display_type IS NULL OR display_type = ''"
                )
            )
        if "is_active" in refreshed_columns:
            conn.execute(text("UPDATE honors SET is_active = TRUE WHERE is_active IS NULL"))
        if "is_featured" in refreshed_columns:
            conn.execute(text("UPDATE honors SET is_featured = FALSE WHERE is_featured IS NULL"))
        if "slug" in refreshed_columns:
            conn.execute(text("UPDATE honors SET slug = 'honor-' || id WHERE slug IS NULL OR slug = ''"))

        if "language_id" in refreshed_columns:
            conn.execute(text("UPDATE honors SET language_id = 1 WHERE language_id IS NULL"))
            try:
                conn.execute(text("ALTER TABLE honors ALTER COLUMN language_id SET DEFAULT 1"))
            except Exception:
                pass


def ensure_banners_schema() -> None:
    with engine.begin() as conn:
        inspector = inspect(conn)
        table_names = set(inspector.get_table_names())
        if "banners" not in table_names:
            return

        column_names = {column["name"] for column in inspector.get_columns("banners")}
        columns_to_add = [
            ("focus_x", "DOUBLE PRECISION"),
            ("focus_y", "DOUBLE PRECISION"),
        ]

        for column_name, column_type in columns_to_add:
            if column_name in column_names:
                continue
            conn.execute(text(f"ALTER TABLE banners ADD COLUMN {column_name} {column_type}"))

        refreshed_columns = {column["name"] for column in inspect(conn).get_columns("banners")}

        if "focus_x" in refreshed_columns:
            conn.execute(text("UPDATE banners SET focus_x = 50 WHERE focus_x IS NULL"))
            try:
                conn.execute(text("ALTER TABLE banners ALTER COLUMN focus_x SET DEFAULT 50"))
            except Exception:
                pass

        if "focus_y" in refreshed_columns:
            conn.execute(text("UPDATE banners SET focus_y = 50 WHERE focus_y IS NULL"))
            try:
                conn.execute(text("ALTER TABLE banners ALTER COLUMN focus_y SET DEFAULT 50"))
            except Exception:
                pass


def ensure_project_case_schema() -> None:
    with engine.begin() as conn:
        inspector = inspect(conn)
        table_names = set(inspector.get_table_names())
        if "projects" not in table_names:
            return

        column_names = {column["name"] for column in inspector.get_columns("projects")}
        columns_to_add = [
            ("legacy_detail_id", "VARCHAR(32)"),
            ("legacy_detail_href", "VARCHAR(500)"),
        ]

        for column_name, column_type in columns_to_add:
            if column_name in column_names:
                continue
            conn.execute(text(f"ALTER TABLE projects ADD COLUMN {column_name} {column_type}"))

        refreshed_columns = {column["name"] for column in inspect(conn).get_columns("projects")}

        if "legacy_detail_id" in refreshed_columns and "meta_title" in refreshed_columns:
            conn.execute(
                text(
                    "UPDATE projects "
                    "SET legacy_detail_id = REPLACE(meta_title, 'legacy-detail:', '') "
                    "WHERE legacy_detail_id IS NULL "
                    "AND meta_title IS NOT NULL "
                    "AND meta_title LIKE 'legacy-detail:%'"
                )
            )

        if "legacy_detail_href" in refreshed_columns and "meta_description" in refreshed_columns:
            conn.execute(
                text(
                    "UPDATE projects "
                    "SET legacy_detail_href = meta_description "
                    "WHERE legacy_detail_href IS NULL "
                    "AND meta_description IS NOT NULL "
                    "AND meta_description LIKE '%/project_detail/%'"
                )
            )


def seed_basics(session: Session) -> None:
    languages = session.scalars(select(Language)).all()
    if not languages:
        session.add_all(
            [
                Language(code="en", name="English", is_default=True, status="active"),
                Language(code="vi", name="Vietnamese", is_default=False, status="active"),
                Language(code="zh", name="Chinese", is_default=False, status="active"),
            ]
        )

    session.flush()

    language_by_code = {language.code: language for language in session.scalars(select(Language)).all()}
    default_language = language_by_code.get("en") or next(iter(language_by_code.values()))
    default_language_id = default_language.id if default_language else None

    seed_site_settings(session=session, language_id=default_language_id)
    if default_language_id is not None:
        media_by_key = seed_media_assets(session=session)
        seed_pages(session=session, language_id=default_language_id, media_by_key=media_by_key)
        seed_banners(session=session, language_id=default_language_id, media_by_key=media_by_key)
        seed_navigation(session=session, language_id=default_language_id)
        seed_honors(session=session)
        seed_contacts(session=session, language_id=default_language_id)
        seed_about_page(session=session, language_id=default_language_id)
    seed_product_categories(session=session)
    seed_products(session=session)
    seed_initial_admin_user(session=session)

    session.commit()


def seed_initial_admin_user(session: Session) -> None:
    existing_admin = session.scalar(select(AdminUser).where(AdminUser.role == "admin"))
    if existing_admin:
        return

    username = settings.initial_admin_username.strip()
    password = settings.initial_admin_password
    if not username or not password:
        return

    session.add(
        AdminUser(
            username=username,
            password_hash=hash_password(password),
            role="admin",
            is_active=True,
        )
    )


def seed_product_categories(session: Session) -> None:
    """Tạo danh mục sản phẩm mẫu nếu chưa có."""
    existing = session.scalars(select(ProductCategory)).all()
    
    # We want to ensure the specific category from the sheet exists
    target_category_name = "Đá mềm Ốp tường linh hoạt"
    target_category_slug = "da-mem-op-tuong-linh-hoat"
    
    # Clear other categories as requested ("cái nào k đúng dl thì xóa")
    for cat in existing:
        if cat.name != target_category_name:
            session.delete(cat)
    
    session.flush()
    
    # Check if target exists
    target = session.scalar(select(ProductCategory).where(ProductCategory.slug == target_category_slug))
    if not target:
        target = ProductCategory(
            name=target_category_name, 
            slug=target_category_slug, 
            description="Danh mục sản phẩm trang trí bao gồm các dòng tấm ốp linh hoạt với đa dạng mẫu mã, kích và bề mặt vân đá tự nhiên.", 
            sort_order=10, 
            is_active=True
        )
        session.add(target)
    session.flush()


def seed_media_assets(session: Session) -> dict[str, MediaAsset]:

    media_seed = [
        {
            "key": "hero-home",
            "uuid": "seed-hero-home",
            "file_name": "hero-home.jpg",
            "url": "https://images.unsplash.com/photo-1497366754035-f200968a6e72?auto=format&fit=crop&w=1600&q=80",
            "storage_path": "seed/hero-home.jpg",
            "asset_type": "image",
            "mime_type": "image/jpeg",
            "width": 1600,
            "height": 900,
            "size": 248320,
            "alt_text": "Modern corporate building lobby",
            "title": "Corporate hero image",
            "status": "active",
        },
        {
            "key": "about-section",
            "uuid": "seed-about-section",
            "file_name": "about-section.jpg",
            "url": "https://images.unsplash.com/photo-1520607162513-77705c0f0d4a?auto=format&fit=crop&w=1200&q=80",
            "storage_path": "seed/about-section.jpg",
            "asset_type": "image",
            "mime_type": "image/jpeg",
            "width": 1200,
            "height": 800,
            "size": 196410,
            "alt_text": "Executive meeting room with planning board",
            "title": "About section image",
            "status": "active",
        },
        {
            "key": "contact-map",
            "uuid": "seed-contact-map",
            "file_name": "contact-map.jpg",
            "url": "https://images.unsplash.com/photo-1486406146926-c627a92ad1ab?auto=format&fit=crop&w=1200&q=80",
            "storage_path": "seed/contact-map.jpg",
            "asset_type": "image",
            "mime_type": "image/jpeg",
            "width": 1200,
            "height": 800,
            "size": 184220,
            "alt_text": "City office exterior",
            "title": "Contact office image",
            "status": "active",
        },
    ]

    existing_by_uuid = {item.uuid: item for item in session.scalars(select(MediaAsset)).all()}
    media_by_key: dict[str, MediaAsset] = {}

    for item in media_seed:
        record = existing_by_uuid.get(item["uuid"])
        if not record:
            record = MediaAsset(uuid=item["uuid"], url=item["url"], asset_type=item["asset_type"])

        record.file_name = item["file_name"]
        record.url = item["url"]
        record.storage_path = item["storage_path"]
        record.asset_type = item["asset_type"]
        record.mime_type = item["mime_type"]
        record.width = item["width"]
        record.height = item["height"]
        record.size = item["size"]
        record.alt_text = item["alt_text"]
        record.title = item["title"]
        record.status = item["status"]
        session.add(record)
        session.flush()
        media_by_key[item["key"]] = record

    return media_by_key


def seed_site_settings(session: Session, language_id: int | None) -> None:
    settings_seed = [
        ("site_name", "THIÊN ĐỒNG VIỆT NAM", "general", "Public site display name"),
        ("site_tagline", "UY TÍN TỪ NHỮNG ĐIỀU NHỎ NHẤT", "general", "Short tagline for header/footer"),
        ("homepage_hero_title", "Giải pháp vật liệu ốp lát hiện đại & linh hoạt.", "homepage", "Hero headline for the landing page"),
        (
            "homepage_hero_subtitle",
            "Chuyên cung cấp các dòng đá mềm, tấm ốp linh hoạt cao cấp cho không gian sống và công trình hiện đại.",
            "homepage",
            "Hero subtitle for the landing page",
        ),
        ("homepage_primary_cta", "Explore Our Story", "homepage", "Primary CTA label"),
        ("homepage_primary_cta_link", "/about/company-introduction", "homepage", "Primary CTA target"),
        ("footer_hotline_label", "Hotline", "footer", "Label displayed before hotline"),
        ("footer_email_label", "Email", "footer", "Label displayed before company email"),
        ("seo_default_title", "China Decor | Corporate Landing Page", "seo", "Default SEO title"),
        (
            "seo_default_description",
            "China Decor corporate landing page showcasing company profile, services, honors, videos, and contact information.",
            "seo",
            "Default SEO description",
        ),
        (
            "company_address",
            "52 Ấp Đồng Chinh, Phước Hòa, Phú Giáo, Bình Dương",
            "contact",
            "Company headquarters address",
        ),
        (
            "company_map_url",
            "https://www.google.com/maps?q=11.198667,106.719694",
            "contact",
            "Public map embed URL for head office",
        ),
        ("company_phone", "0948.929.744", "contact", "Main hotline"),
        ("company_email", "thiendongintl@gmail.com", "contact", "Main contact email"),
        ("copyright_text", "© 2024 THIÊN ĐỒNG VIỆT NAM. Tất cả quyền được bảo lưu.", "legal", "Footer copyright line"),
        ("beian_text", "", "legal", "备案号"),
        ("beian_url", "", "legal", "备案跳转地址"),
        ("technical_support_text", "Hỗ trợ kỹ thuật: THIÊN ĐỒNG VIỆT NAM", "legal", "Footer support text"),
    ]

    settings_by_key = {item.config_key: item for item in session.scalars(select(SiteSetting)).all()}
    now = datetime.now(timezone.utc)

    for config_key, config_value, group_name, description in settings_seed:
        if config_key in settings_by_key:
            record = settings_by_key[config_key]
            record.config_value = config_value
            record.group_name = group_name
            record.description = description
            record.language_id = language_id
            record.updated_at = now
            session.add(record)
            continue

        session.add(
            SiteSetting(
                config_key=config_key,
                config_value=config_value,
                language_id=language_id,
                group_name=group_name,
                description=description,
                updated_at=now,
            )
        )


def seed_pages(session: Session, language_id: int, media_by_key: dict[str, MediaAsset]) -> None:
    pages_seed = [
        {
            "slug": "contact",
            "title": "Contact Us",
            "summary": "Reach China Decor through our headquarters, hotline, email, or inquiry form.",
            "body": "Get in touch with our corporate team for project consulting, strategic partnerships, and media inquiries.",
            "page_type": "contact",
            "status": "published",
            "meta_title": "Contact China Decor",
            "meta_description": "Contact China Decor through our headquarters information, map, hotline, and email.",
            "sort_order": 20,
            "sections": [
                {
                    "anchor": "ctn1",
                    "title": "Corporate Inquiry",
                    "content": "Use the inquiry form to contact our business development and project advisory team. We respond to qualified requests within one business day.",
                    "image_id": media_by_key["contact-map"].id,
                    "section_type": "contact_form",
                    "sort_order": 10,
                },
                {
                    "anchor": "ctn2",
                    "title": "Head Office",
                    "content": "Visit our Beijing headquarters for scheduled meetings, partnership discussions, and project presentations.",
                    "image_id": media_by_key["contact-map"].id,
                    "section_type": "location",
                    "sort_order": 20,
                },
            ],
        },
        {
            "slug": "privacy-policy",
            "title": "Privacy Policy",
            "summary": "Guidelines on data handling and visitor privacy protection.",
            "body": "This privacy policy explains how China Decor collects, processes, and safeguards information submitted through our website.",
            "page_type": "legal",
            "status": "published",
            "meta_title": "Privacy Policy | China Decor",
            "meta_description": "Read the China Decor privacy policy for information about website data handling and visitor rights.",
            "sort_order": 30,
            "sections": [
                {
                    "anchor": "page1",
                    "title": "Data Collection",
                    "content": "We collect only the information necessary to respond to inquiries, improve user experience, and maintain secure website operations.",
                    "image_id": None,
                    "section_type": "legal_text",
                    "sort_order": 10,
                }
            ],
        },
    ]


    pages_by_slug = {
        (page.slug, page.language_id): page
        for page in session.scalars(select(Page).where(Page.language_id == language_id)).all()
    }

    for page_seed in pages_seed:
        key = (page_seed["slug"], language_id)
        page = pages_by_slug.get(key)
        if not page:
            page = Page(slug=page_seed["slug"], language_id=language_id)

        page.title = page_seed["title"]
        page.summary = page_seed["summary"]
        page.body = page_seed["body"]
        page.page_type = page_seed["page_type"]
        page.parent_id = None
        page.status = page_seed["status"]
        page.meta_title = page_seed["meta_title"]
        page.meta_description = page_seed["meta_description"]
        page.sort_order = page_seed["sort_order"]
        session.add(page)
        session.flush()

        existing_sections = {
            (section.anchor or "", section.section_type or ""): section
            for section in session.scalars(select(PageSection).where(PageSection.page_id == page.id)).all()
        }

        for section_seed in page_seed["sections"]:
            section_key = (section_seed["anchor"] or "", section_seed["section_type"] or "")
            section = existing_sections.get(section_key)
            if not section:
                section = PageSection(page_id=page.id)

            section.anchor = section_seed["anchor"]
            section.title = section_seed["title"]
            section.content = section_seed["content"]
            section.image_id = section_seed["image_id"]
            section.section_type = section_seed["section_type"]
            section.sort_order = section_seed["sort_order"]
            session.add(section)

    legacy_about_page = session.scalar(
        select(Page).where(Page.slug == "about/company-introduction", Page.language_id == language_id)
    )
    if legacy_about_page:
        session.delete(legacy_about_page)



def seed_banners(session: Session, language_id: int, media_by_key: dict[str, MediaAsset]) -> None:
    banners_seed = [
        {
            "title": "Build premium corporate environments",
            "subtitle": "Integrated design, construction, and delivery for flagship commercial spaces.",
            "body": "From concept strategy to on-site execution, China Decor supports complex projects with a premium delivery mindset.",
            "image_id": media_by_key["hero-home"].id,
            "link": "/about/company-introduction",
            "button_text": "Discover More",
            "banner_type": "hero",
            "sort_order": 10,
            "is_active": True,
        },
        {
            "title": "Talk to our project advisory team",
            "subtitle": "Share your scope, timeline, and spatial goals for an initial consultation.",
            "body": "Our team helps enterprises, hospitality groups, and public-sector organizations map an efficient delivery roadmap.",
            "image_id": media_by_key["contact-map"].id,
            "link": "/contact",
            "button_text": "Contact Us",
            "banner_type": "cta",
            "sort_order": 20,
            "is_active": True,
        },
    ]

    existing_banners = {
        (banner.title or "", banner.language_id): banner
        for banner in session.scalars(select(Banner).where(Banner.language_id == language_id)).all()
    }

    for banner_seed in banners_seed:
        key = (banner_seed["title"], language_id)
        banner = existing_banners.get(key)
        if not banner:
            banner = Banner(language_id=language_id)

        banner.title = banner_seed["title"]
        banner.subtitle = banner_seed["subtitle"]
        banner.body = banner_seed["body"]
        banner.image_id = banner_seed["image_id"]
        banner.link = banner_seed["link"]
        banner.button_text = banner_seed["button_text"]
        banner.banner_type = banner_seed["banner_type"]
        banner.sort_order = banner_seed["sort_order"]
        banner.is_active = banner_seed["is_active"]
        session.add(banner)


def seed_honors(session: Session) -> None:
    categories_seed = [
        {
            "name": "Qualification Certificate",
            "slug": "qualification-certificate",
            "type": "qualification_certificate",
            "parent_slug": None,
            "description": "Qualification and compliance certificates.",
            "sort_order": 0,
            "is_active": True,
        },
        {
            "name": "Honorary Awards",
            "slug": "honorary-awards",
            "type": "awards_group",
            "parent_slug": None,
            "description": "Awards grouped by corporate and project tabs.",
            "sort_order": 10,
            "is_active": True,
        },
        {
            "name": "Corporate Honors",
            "slug": "corporate-honors",
            "type": "corporate_honors",
            "parent_slug": "honorary-awards",
            "description": "Corporate-level honors and association awards.",
            "sort_order": 20,
            "is_active": True,
        },
        {
            "name": "Project Honors",
            "slug": "project-honors",
            "type": "project_honors",
            "parent_slug": "honorary-awards",
            "description": "Project-specific honors and certifications.",
            "sort_order": 30,
            "is_active": True,
        },
    ]

    categories_by_slug = {
        category.slug: category for category in session.scalars(select(HonorCategory)).all()
    }

    for seed in categories_seed:
        category = categories_by_slug.get(seed["slug"])
        if category:
            continue

        parent_slug = seed["parent_slug"]
        parent_id = categories_by_slug[parent_slug].id if parent_slug and parent_slug in categories_by_slug else None
        category = HonorCategory(
            slug=seed["slug"],
            name=seed["name"],
            type=seed["type"],
            parent_id=parent_id,
            description=seed["description"],
            sort_order=seed["sort_order"],
            is_active=seed["is_active"],
            deleted_at=None,
        )
        session.add(category)
        session.flush()
        categories_by_slug[seed["slug"]] = category

    honors_seed = [
        {
            "title": "Contract enterprise certificate",
            "slug": "contract-enterprise-certificate",
            "category_slug": "qualification-certificate",
            "short_description": "Qualification certificate for enterprise credibility.",
            "image_url": "https://en.sinodecor.com/portal-local/ngc202304190002/cms/image/29559d05-0b20-4044-9830-81c74dd9e70d.jpg",
            "year": 2023,
            "issued_by": "Beijing Authority",
            "display_type": "qualification_certificate",
            "sort_order": 0,
        },
        {
            "title": "High-tech enterprises",
            "slug": "high-tech-enterprises",
            "category_slug": "qualification-certificate",
            "short_description": "Recognized as high-tech enterprise.",
            "image_url": "https://en.sinodecor.com/portal-local/ngc202304190002/cms/image/f1e6b95b-00f9-458f-bdfc-9e39d93c72d4.jpg",
            "year": 2022,
            "issued_by": "National Technology Program",
            "display_type": "qualification_certificate",
            "sort_order": 10,
        },
        {
            "title": "Civilized organization of the central state organs",
            "slug": "civilized-organization-central-state-organs",
            "category_slug": "corporate-honors",
            "short_description": "Corporate award for organizational excellence.",
            "image_url": "https://en.sinodecor.com/portal-local/ngc202304190002/cms/image/d13d5d1c-7bc2-41de-b0e0-2e14da8b3b72.png",
            "year": 2021,
            "issued_by": "Central Committee",
            "display_type": "corporate_honors",
            "sort_order": 20,
        },
        {
            "title": "Vice-chairman unit of CBDA",
            "slug": "vice-chairman-unit-cbda",
            "category_slug": "corporate-honors",
            "short_description": "Corporate distinction from CBDA.",
            "image_url": "https://en.sinodecor.com/portal-local/ngc202304190002/cms/image/1dffe04b-f900-4fde-b8f1-95a451cfdb2c.jpg",
            "year": 2020,
            "issued_by": "CBDA",
            "display_type": "corporate_honors",
            "sort_order": 30,
        },
        {
            "title": "China building decoration industry top 100 enterprises",
            "slug": "china-building-decoration-top-100-enterprises",
            "category_slug": "project-honors",
            "short_description": "Project honor for top 100 excellence.",
            "image_url": "https://en.sinodecor.com/portal-local/ngc202304190002/cms/image/7539e162-e7f1-4e45-aa80-09b8a6d2ee19.jpg",
            "year": 2024,
            "issued_by": "China Building Decoration Association",
            "display_type": "project_honors",
            "sort_order": 40,
        },
        {
            "title": "Asian-Pacific best design enterprise",
            "slug": "asian-pacific-best-design-enterprise",
            "category_slug": "project-honors",
            "short_description": "Regional project design excellence recognition.",
            "image_url": "https://en.sinodecor.com/portal-local/ngc202304190002/cms/image/6cf5ccb3-d681-455c-a85b-1f962020d720.jpg",
            "year": 2023,
            "issued_by": "AP Design Council",
            "display_type": "project_honors",
            "sort_order": 50,
        },
        {
            "title": "Environmental management system certification",
            "slug": "environmental-management-system-certification",
            "category_slug": "qualification-certificate",
            "short_description": "Environmental management system certificate.",
            "image_url": "https://en.sinodecor.com/portal-local/ngc202304190002/cms/image/7181e0bb-edfa-4596-8f78-a59e8cab934c.jpg",
            "year": None,
            "issued_by": "Environmental Certification Authority",
            "display_type": "qualification_certificate",
            "sort_order": 60,
        },
        {
            "title": "China quality integrity AAA enterprises",
            "slug": "china-quality-integrity-aaa-enterprises",
            "category_slug": "qualification-certificate",
            "short_description": "AAA quality integrity enterprise recognition.",
            "image_url": "https://en.sinodecor.com/portal-local/ngc202304190002/cms/image/00a72575-94ca-4e12-91d1-e33d739fcac4.jpg",
            "year": None,
            "issued_by": "Quality Integrity Program",
            "display_type": "qualification_certificate",
            "sort_order": 70,
        },
        {
            "title": "Beijing \"innovative\" small and medium-sized enterprises",
            "slug": "beijing-innovative-small-and-medium-sized-enterprises",
            "category_slug": "qualification-certificate",
            "short_description": "Innovation recognition for Beijing SMEs.",
            "image_url": "https://en.sinodecor.com/portal-local/ngc202304190002/cms/image/3c1ce1e0-e0c7-455f-b01d-6ef174ea3124.jpg",
            "year": None,
            "issued_by": "Beijing SME Innovation Program",
            "display_type": "qualification_certificate",
            "sort_order": 80,
        },
        {
            "title": "PROMISE-KEEPING ENTERPRISE OF BAIC",
            "slug": "promise-keeping-enterprise-of-baic",
            "category_slug": "corporate-honors",
            "short_description": "Corporate credibility and trustkeeping distinction.",
            "image_url": "https://en.sinodecor.com/portal-local/ngc202304190002/cms/image/e6bb6639-ee6d-4081-b382-bea768d7ac0e.png",
            "year": None,
            "issued_by": "BAIC",
            "display_type": "corporate_honors",
            "sort_order": 90,
        },
        {
            "title": "China building decoration industry for 30 years pioneering enterprises",
            "slug": "china-building-decoration-industry-30-years-pioneering-enterprises",
            "category_slug": "corporate-honors",
            "short_description": "Pioneering enterprise honor in building decoration industry.",
            "image_url": "https://en.sinodecor.com/portal-local/ngc202304190002/cms/image/d8e4fa85-2bb3-48b8-a4fe-8e0ef6c325e7.jpg",
            "year": None,
            "issued_by": "China Building Decoration Industry",
            "display_type": "corporate_honors",
            "sort_order": 100,
        },
        {
            "title": "2016 China Architectural Engineering Decoration Award",
            "slug": "2016-china-architectural-engineering-decoration-award",
            "category_slug": "project-honors",
            "short_description": "Project-level national architectural engineering decoration award.",
            "image_url": "https://en.sinodecor.com/portal-local/ngc202304190002/cms/image/0a30450e-a19d-42a9-989b-53da9e612b9d.jpg",
            "year": 2016,
            "issued_by": "China Architectural Decoration Association",
            "display_type": "project_honors",
            "sort_order": 110,
        },
        {
            "title": "2020 China Architectural Engineering Decoration Award",
            "slug": "2020-china-architectural-engineering-decoration-award",
            "category_slug": "project-honors",
            "short_description": "Project-level national architectural engineering decoration award.",
            "image_url": "https://en.sinodecor.com/portal-local/ngc202304190002/cms/image/e6959d45-ef96-4782-bab8-d5ed26a89034.jpg",
            "year": 2020,
            "issued_by": "China Architectural Decoration Association",
            "display_type": "project_honors",
            "sort_order": 120,
        },
        {
            "title": "2022 Excellent design of Beijing Architectural Decoration Project",
            "slug": "2022-excellent-design-beijing-architectural-decoration-project",
            "category_slug": "project-honors",
            "short_description": "Excellent design recognition for Beijing architectural decoration project.",
            "image_url": "https://en.sinodecor.com/portal-local/ngc202304190002/cms/image/6c9316c9-711b-45f3-9aa6-5320468647eb.jpg",
            "year": 2022,
            "issued_by": "Beijing Architectural Decoration Association",
            "display_type": "project_honors",
            "sort_order": 130,
        },
    ]

    honors_by_slug = {honor.slug: honor for honor in session.scalars(select(Honor)).all()}
    for seed in honors_seed:
        honor = honors_by_slug.get(seed["slug"])
        if honor:
            continue

        honor = Honor(
            category_id=categories_by_slug[seed["category_slug"]].id,
            title=seed["title"],
            slug=seed["slug"],
            short_description=seed["short_description"],
            image_url=seed["image_url"],
            year=seed["year"],
            issued_by=seed["issued_by"],
            display_type=seed["display_type"],
            sort_order=seed["sort_order"],
            is_featured=False,
            is_active=True,
            deleted_at=None,
        )
        session.add(honor)






def seed_contacts(session: Session, language_id: int) -> None:
    existing_contact = session.scalar(
        select(Contact).where(Contact.language_id == language_id).order_by(Contact.is_primary.desc(), Contact.id.asc())
    )
    if existing_contact:
        if not existing_contact.is_primary:
            existing_contact.is_primary = True
            session.add(existing_contact)
        return

    session.add(
        Contact(
            name="China National Decoration Co.,Ltd",
            contact_type="head_office",
            address="5F, Block C, Hehuamingcheng Building, No.7 Jianguomen South Street, Dongcheng District, Beijing",
            postal_code="100005",
            phone="010-65269998",
            email="CNDC@sinodecor.com",
            map_url="https://www.openstreetmap.org/export/embed.html?bbox=116.4378%2C39.9087%2C116.4439%2C39.9124&layer=mapnik&marker=39.910466%2C116.44079",
            latitude="39.910466",
            longitude="116.44079",
            is_primary=True,
            language_id=language_id,
        )
    )


def seed_navigation(session: Session, language_id: int) -> None:
    header_items = [
        {"title": "Trang Chủ", "url": "/#ctn1", "sort_order": 0},
        {
            "title": "Giới Thiệu",
            "url": "/about/company-introduction#page1",
            "sort_order": 10,
            "children": [
                {"title": "Về Chúng Tôi", "url": "/about/company-introduction#page2", "sort_order": 0},
                {"title": "Tầm Nhìn & Sứ Mệnh", "url": "/about/chairman-speech#page3", "sort_order": 10},
                {"title": "Sơ Đồ Tổ Chức", "url": "/about/organization-chart#page4", "sort_order": 20},
                {"title": "Giá Trị Cốt Lõi", "url": "/about/corporate-culture#page5", "sort_order": 30},
                {"title": "Lịch Sử Phát Triển", "url": "/about/development-course#page6", "sort_order": 40},
                {"title": "Ban Lãnh Đạo", "url": "/about/leadership-care#page7", "sort_order": 50},
                {"title": "Đối Tác", "url": "/about/cooperative-partner#page8", "sort_order": 60},
            ],
        },
        {
            "title": "Sản Phẩm",
            "url": "/products",
            "sort_order": 20,
        },
        {
            "title": "Dự Án",
            "url": "/project-case",
            "sort_order": 30,
        },
        {
<<<<<<< HEAD
            "title": "Tin Tức",
            "url": "/news/corporate-news",
            "sort_order": 40,
=======
            "title": "News Center",
            "url": "/news",
            "sort_order": 40,
            "children": [
                {"title": "News Center", "url": "/news", "sort_order": 0},
            ],
>>>>>>> de96dfd (tintuc: dang lam do)
        },
        {
            "title": "Liên Hệ",
            "url": "/contact",
            "sort_order": 50,
        },
    ]
    footer_items = [
        {
            "title": "Giới Thiệu",
            "url": "/about/company-introduction#page2",
            "sort_order": 0,
            "children": [
                {"title": "Về Chúng Tôi", "url": "/about/company-introduction#page2", "sort_order": 0},
                {"title": "Tầm Nhìn & Sứ Mệnh", "url": "/about/chairman-speech#page3", "sort_order": 10},
                {"title": "Giá Trị Cốt Lõi", "url": "/about/corporate-culture#page5", "sort_order": 30},
                {"title": "Lịch Sử Phát Triển", "url": "/about/development-course#page6", "sort_order": 40},
            ],
        },
        {
            "title": "Sản Phẩm",
            "url": "/products",
            "sort_order": 20,
        },
        {
<<<<<<< HEAD
            "title": "Liên Hệ",
=======
            "title": "News Center",
            "url": "/news",
            "sort_order": 30,
            "children": [
                {"title": "News Center", "url": "/news", "sort_order": 0},
            ],
        },
        {
            "title": "Social Responsibility",
            "url": "/social-responsibility",
            "sort_order": 40,
        },
        {
            "title": "Contact Us",
>>>>>>> de96dfd (tintuc: dang lam do)
            "url": "/contact#ctn2",
            "sort_order": 50,
        },
    ]

    header_menu = _upsert_menu(
        session=session,
        name="Main Navigation",
        location="header",
        language_id=language_id,
        is_active=True,
    )
    footer_menu = _upsert_menu(
        session=session,
        name="Footer Navigation",
        location="footer",
        language_id=language_id,
        is_active=True,
    )

    _replace_menu_items(session=session, menu=header_menu, nodes=header_items)
    _replace_menu_items(session=session, menu=footer_menu, nodes=footer_items)


def _upsert_menu(session: Session, name: str, location: str, language_id: int, is_active: bool) -> Menu:
    record = session.scalar(
        select(Menu).where(
            Menu.language_id == language_id,
            Menu.location == location,
        )
    )
    if not record:
        record = Menu(name=name, location=location, language_id=language_id, is_active=is_active)
        session.add(record)
        session.flush()
        return record

    record.name = name
    record.is_active = is_active
    session.add(record)
    session.flush()
    return record


def _replace_menu_items(session: Session, menu: Menu, nodes: list[dict], parent_id: int | None = None) -> None:
    if parent_id is None:
        session.execute(delete(MenuItem).where(MenuItem.menu_id == menu.id))
        session.flush()

    for index, node in enumerate(nodes):
        item = MenuItem(
            menu_id=menu.id,
            parent_id=parent_id,
            title=node["title"],
            url=node["url"],
            target=node.get("target"),
            item_type=node.get("item_type"),
            page_id=node.get("page_id"),
            anchor=node.get("anchor"),
            sort_order=node.get("sort_order", index * 10),
        )
        session.add(item)
        session.flush()

        children = node.get("children") or []
        if children:
            _replace_menu_items(session=session, menu=menu, nodes=children, parent_id=item.id)
