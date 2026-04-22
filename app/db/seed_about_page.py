"""
Sprint 2 - Seed About page CMS data.

Tạo 1 page canonical slug="about" với đầy đủ:
- 8 page_sections
- 20 content_blocks
- ~100+ content_block_items

Dữ liệu lấy thẳng từ AboutPage.vue hard-code.
Thiết kế idempotent: chạy lại không tạo duplicate.
"""

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.models.content import ContentBlock, ContentBlockItem, Page, PageSection


# ---------------------------------------------------------------------------
# Helpers - idempotent get-or-create
# ---------------------------------------------------------------------------

def _get_or_create_page(session: Session, slug: str, language_id: int, **kwargs) -> Page:
    page = session.scalar(
        select(Page).where(Page.slug == slug, Page.language_id == language_id)
    )
    if not page:
        page = Page(slug=slug, language_id=language_id)
    for k, v in kwargs.items():
        setattr(page, k, v)
    session.add(page)
    session.flush()
    return page


def _get_or_create_section(session: Session, page_id: int, anchor: str, **kwargs) -> PageSection:
    section = session.scalar(
        select(PageSection).where(
            PageSection.page_id == page_id,
            PageSection.anchor == anchor,
        )
    )
    if not section:
        section = PageSection(page_id=page_id, anchor=anchor)
    for k, v in kwargs.items():
        setattr(section, k, v)
    session.add(section)
    session.flush()
    return section


def _get_or_create_block(
    session: Session,
    entity_type: str,
    entity_id: int,
    block_key: str,
    language_id: int | None,
    **kwargs,
) -> ContentBlock:
    filters = [
        ContentBlock.entity_type == entity_type,
        ContentBlock.entity_id == entity_id,
        ContentBlock.block_key == block_key,
    ]
    if language_id is not None:
        filters.append(
            or_(ContentBlock.language_id == language_id, ContentBlock.language_id.is_(None))
        )
    else:
        filters.append(ContentBlock.language_id.is_(None))

    block = session.scalar(select(ContentBlock).where(*filters))
    if not block:
        block = ContentBlock(
            entity_type=entity_type,
            entity_id=entity_id,
            block_key=block_key,
            language_id=language_id,
        )
    for k, v in kwargs.items():
        setattr(block, k, v)
    session.add(block)
    session.flush()
    return block


def _get_or_create_item(session: Session, block_id: int, item_key: str, **kwargs) -> ContentBlockItem:
    item = session.scalar(
        select(ContentBlockItem).where(
            ContentBlockItem.block_id == block_id,
            ContentBlockItem.item_key == item_key,
        )
    )
    if not item:
        item = ContentBlockItem(block_id=block_id, item_key=item_key)
    for k, v in kwargs.items():
        setattr(item, k, v)
    session.add(item)
    session.flush()
    return item


# ---------------------------------------------------------------------------
# Image base URLs (same as AboutPage.vue)
# ---------------------------------------------------------------------------
_IMG_BASE = "https://en.sinodecor.com/portal-local/ngc202304190002/cms/image"
_REPO_BASE = "https://en.sinodecor.com/repository/portal-local/ngc202304190002/cms/image"


def _img(f: str) -> str:
    return f"{_IMG_BASE}/{f}"


def _repo(f: str) -> str:
    return f"{_REPO_BASE}/{f}"


# ---------------------------------------------------------------------------
# Main seed function
# ---------------------------------------------------------------------------

def seed_about_page(session: Session, language_id: int) -> None:
    """Seed About page with all sections, blocks, and items."""

    # 1. Page
    about = _get_or_create_page(
        session,
        slug="about",
        language_id=language_id,
        title="Giới Thiệu",
        summary="CÔNG TY TNHH THƯƠNG MẠI QUỐC TẾ THIÊN ĐỒNG VIỆT NAM chuyên cung cấp các dòng đá mềm – tấm ốp linh hoạt cao cấp.",
        body=None,
        page_type="about",
        parent_id=None,
        status="published",
        meta_title="Giới Thiệu | THIÊN ĐỒNG VIỆT NAM",
        meta_description="Thông tin về Công ty TNHH Thương mại Quốc tế Thiên Đồng Việt Nam - chuyên cung cấp đá mềm, tấm ốp linh hoạt cao cấp.",
        sort_order=5,
    )
    pid = about.id

    # 2. Sections
    sections_seed = [
        ("hero", "Giới Thiệu Thiên Đồng", "hero", 10),
        ("company_introduction", "Về Chúng Tôi", "content", 20),
        ("chairman_speech", "Tầm Nhìn & Chiến Lược", "content", 30),
        ("organization_chart", "Sơ Đồ Tổ Chức", "media", 40),
        ("corporate_culture", "Văn Hóa Doanh Nghiệp", "content", 50),
        ("development_course", "Lịch Sử Phát Triển", "timeline", 60),
        ("leadership_care", "Ban Lãnh Đạo", "gallery", 70),
        ("cooperative_partner", "Đối Tác Hợp Tác", "partners", 80),
    ]
    for anchor, title, section_type, sort_order in sections_seed:
        _get_or_create_section(
            session,
            page_id=pid,
            anchor=anchor,
            title=title,
            section_type=section_type,
            sort_order=sort_order,
            content=None,
            image_id=None,
        )

    # 3 & 4. Blocks + Items
    _seed_hero_blocks(session, pid, language_id)
    _seed_intro_blocks(session, pid, language_id)
    _seed_speech_blocks(session, pid, language_id)
    _seed_org_chart_blocks(session, pid, language_id)
    _seed_culture_blocks(session, pid, language_id)
    _seed_timeline_blocks(session, pid, language_id)
    _seed_leadership_blocks(session, pid, language_id)
    _seed_partner_blocks(session, pid, language_id)


# ===========================================================================
# Block + Item seeders per section
# ===========================================================================

def _seed_hero_blocks(session: Session, page_id: int, lang_id: int) -> None:
    # hero_summary
    b = _get_or_create_block(
        session, "page", page_id, "hero_summary", lang_id,
        title="Tổng quan giới thiệu", block_type="key_value", sort_order=10,
    )
    _get_or_create_item(
        session, b.id, "headline",
        title="CÔNG TY TNHH THƯƠNG MẠI QUỐC TẾ THIÊN ĐỒNG VIỆT NAM",
        sort_order=10,
    )
    _get_or_create_item(
        session, b.id, "description",
        title="Mô tả hero",
        content="Thiên Đồng Việt Nam - Uy tín từ những điều nhỏ nhất. Chuyên cung cấp các dòng đá mềm và tấm ốp tường linh hoạt cho không gian hiện đại.",
        sort_order=20,
    )
    _get_or_create_item(
        session, b.id, "cover_image",
        title="Banner đầu trang",
        metadata_json={"src": "/images/banner/banner3.jpg"},
        sort_order=30,
    )

    # hero_nav
    b = _get_or_create_block(
        session, "page", page_id, "hero_nav", lang_id,
        title="About Navigation Tabs", block_type="nav_list", sort_order=20,
    )
    nav_items = [
        ("company_introduction", "Giới Thiệu"),
        ("chairman_speech", "Tầm Nhìn"),
        ("organization_chart", "Sơ Đồ Tổ Chức"),
        ("corporate_culture", "Giá Trị Cốt Lõi"),
        ("development_course", "Lịch Sử"),
        ("leadership_care", "Ban Lãnh Đạo"),
    ]
    for idx, (key, label) in enumerate(nav_items):
        _get_or_create_item(
            session, b.id, key,
            title=label,
            sort_order=(idx + 1) * 10,
            metadata_json={"target_anchor": key},
        )


def _seed_intro_blocks(session: Session, page_id: int, lang_id: int) -> None:
    # intro_media
    b = _get_or_create_block(
        session, "page", page_id, "intro_media", lang_id,
        title="Giới thiệu công ty", block_type="media", sort_order=30,
    )
    _get_or_create_item(session, b.id, "cover_image",
                        title="Hình ảnh nền mục Giới thiệu",
                        sort_order=10,
                        metadata_json={
                            "src": "https://res.cloudinary.com/db1b15yn4/image/upload/v1776357180/China_web/banner/homepage-banner-05-image.jpg",
                            "legacy_source_url": _img("f1225086-4996-4f1d-886-08f4228a378e.png"),
                        })

    # intro_video
    b = _get_or_create_block(
        session, "page", page_id, "intro_video", lang_id,
        title="Company Introduction Video", block_type="video", sort_order=40,
    )
    _get_or_create_item(session, b.id, "video_button",
                        title="VIDEO +", sort_order=10)
    _get_or_create_item(session, b.id, "video_url",
                        title="Company intro video",
                        link="/images/vd/1fb59345-a995-4408-b03b-e8e38ff258e7.web.mp4",
                        metadata_json={
                            "external_source_url": "https://drive.google.com/file/d/120045rHguHlBfZHH2UnwY58KL8DAUhZv/view?usp=sharing",
                            "media_migration_status": "pending",
                        },
                        sort_order=20)

    # intro_paragraphs
    paragraphs = [
        "CÔNG TY TNHH THƯƠNG MẠI QUỐC TẾ THIÊN ĐỒNG VIỆT NAM chuyên cung cấp các dòng đá mềm – tấm ốp linh hoạt cao cấp, ứng dụng trong trang trí nội thất và ngoại thất hiện đại.",
        "Sản phẩm của chúng tôi mang lại giải pháp thay thế hoàn hảo cho đá tự nhiên truyền thống với ưu điểm nhẹ, linh hoạt, dễ thi công và tiết kiệm chi phí, phù hợp cho nhiều loại công trình từ nhà ở, showroom đến dự án thương mại.",
    ]
    b = _get_or_create_block(
        session, "page", page_id, "intro_paragraphs", lang_id,
        title="Nội dung giới thiệu (Các đoạn văn)", block_type="rich_text_list", sort_order=50,
    )

    # Clear existing items for this block to remove old paragraphs
    session.execute(delete(ContentBlockItem).where(ContentBlockItem.block_id == b.id))

    for idx, text in enumerate(paragraphs):
        _get_or_create_item(
            session, b.id, f"paragraph_{idx + 1}",
            title=f"Đoạn văn giới thiệu số {idx + 1}",
            content=text,
            sort_order=(idx + 1) * 10,
        )


def _seed_speech_blocks(session: Session, page_id: int, lang_id: int) -> None:
    # speech_profile
    b = _get_or_create_block(
        session, "page", page_id, "speech_profile", lang_id,
        title="Tầm Nhìn & Sứ Mệnh", block_type="media", sort_order=60,
    )
    _get_or_create_item(session, b.id, "portrait",
                        title="Hình ảnh Giám đốc",
                        sort_order=10,
                        metadata_json={"src": "https://res.cloudinary.com/db1b15yn4/image/upload/v1776694034/Image_20260418142413_9_3_m65uzj.jpg"})

    # speech_body
    vision = (
        "Trở thành đơn vị tiên phong tại Việt Nam trong lĩnh vực cung cấp vật liệu trang trí linh hoạt, "
        "đặc biệt là đá mềm, hướng đến thị trường quốc tế."
    )
    mission = (
        "Mang đến giải pháp vật liệu ốp lát hiện đại, bền đẹp và tối ưu chi phí, "
        "giúp khách hàng nâng tầm không gian sống và công trình xây dựng."
    )

    b = _get_or_create_block(
        session, "page", page_id, "speech_body", lang_id,
        title="Tầm Nhìn & Sứ Mệnh", block_type="rich_text_list", sort_order=70,
    )

    # Clear existing items for this block
    session.execute(delete(ContentBlockItem).where(ContentBlockItem.block_id == b.id))

    _get_or_create_item(
        session, b.id, "vision",
        title="Tầm nhìn",
        content=vision,
        sort_order=10,
    )
    _get_or_create_item(
        session, b.id, "mission",
        title="Sứ mệnh",
        content=mission,
        sort_order=20,
    )

    # speech_signature - Set to empty to hide
    b = _get_or_create_block(
        session, "page", page_id, "speech_signature", lang_id,
        title="Chairman Signature", block_type="key_value", sort_order=80,
    )
    _get_or_create_item(session, b.id, "sign_title",
                        title="",
                        sort_order=10)
    _get_or_create_item(session, b.id, "sign_name",
                        title="",
                        sort_order=20)


def _seed_org_chart_blocks(session: Session, page_id: int, lang_id: int) -> None:
    b = _get_or_create_block(
        session, "page", page_id, "org_chart_image", lang_id,
        title="Sơ Đồ Tổ Chức", block_type="media", sort_order=90,
    )
    _get_or_create_item(session, b.id, "main_chart",
                        title="Organization chart image",
                        sort_order=10,
                        metadata_json={
                            "src": _img("bcb4ff12-813e-43ef-9669-e5ed2da9a123.png"),
                            "org_chart_text": "Giám đốc | Phòng Kinh doanh | Phòng Marketing | Phòng Kỹ thuật / Thi công | Kế toán – Hành chính",
                        })


def _seed_culture_blocks(session: Session, page_id: int, lang_id: int) -> None:
    culture_data = [
        (
            "culture_values", "Giá trị cốt lõi", 130,
            [
                ("Chất lượng", "Sản phẩm đạt tiêu chuẩn cao"),
                ("Uy tín", "Cam kết đúng tiến độ, đúng chất lượng"),
                ("Đổi mới", "Luôn cập nhật xu hướng vật liệu mới"),
                ("Khách hàng là trung tâm", "Đặt nhu cầu khách hàng lên hàng đầu"),
                ("Hợp tác lâu dài", "Phát triển bền vững cùng đối tác"),
            ],
        ),
    ]

    # Clear existing culture blocks to remove extra tabs
    culture_keys = ["culture_purpose", "culture_mission", "culture_spirit", "culture_values"]

    # 1. Clear items first to avoid ForeignKeyViolation
    session.execute(
        delete(ContentBlockItem).where(
            ContentBlockItem.block_id.in_(
                select(ContentBlock.id).where(
                    ContentBlock.entity_type == "page",
                    ContentBlock.entity_id == page_id,
                    ContentBlock.block_key.in_(culture_keys)
                )
            )
        )
    )

    # 2. Clear blocks
    session.execute(
        delete(ContentBlock).where(
            ContentBlock.entity_type == "page",
            ContentBlock.entity_id == page_id,
            ContentBlock.block_key.in_(culture_keys)
        )
    )
    session.flush()

    for block_key, block_title, sort_order, items in culture_data:
        b = _get_or_create_block(
            session, "page", page_id, block_key, lang_id,
            title=block_title, block_type="bullet_list", sort_order=sort_order,
        )
        for idx, (label, text) in enumerate(items):
            _get_or_create_item(
                session, b.id, f"value_{idx + 1}",
                title=label,
                content=text,
                sort_order=(idx + 1) * 10,
            )


def _seed_timeline_blocks(session: Session, page_id: int, lang_id: int) -> None:
    timeline_entries = [
        ("2024", "", "Thành lập công ty tại Bình Dương", ""),
        ("2024 - nay", "", "Phát triển và phân phối sản phẩm đá mềm, mở rộng mạng lưới khách hàng trong và ngoài nước", ""),
    ]

    b = _get_or_create_block(
        session, "page", page_id, "timeline", lang_id,
        title="Lịch Sử Phát Triển", block_type="timeline", sort_order=140,
    )

    # CLEAR existing items first to remove old milestones
    session.execute(delete(ContentBlockItem).where(ContentBlockItem.block_id == b.id))

    for idx, (year, month, title, image_url) in enumerate(timeline_entries):
        meta = {"year": year, "month": month}
        if image_url:
            meta["image_url"] = image_url
        _get_or_create_item(
            session, b.id, f"milestone_{idx + 1}",
            title=title,
            sort_order=(idx + 1) * 10,
            metadata_json=meta,
        )


def _seed_leadership_blocks(session: Session, page_id: int, lang_id: int) -> None:
    leadership_items = [
        (
            "Giám đốc",
            "https://res.cloudinary.com/db1b15yn4/image/upload/v1776694034/Image_20260418142413_9_3_m65uzj.jpg",
            "Nguyễn Hà Thanh",
        ),
    ]

    # Clear existing items to ensure only one person is shown
    session.execute(
        delete(ContentBlockItem).where(
            ContentBlockItem.block_id.in_(
                select(ContentBlock.id).where(
                    ContentBlock.entity_type == "page",
                    ContentBlock.entity_id == page_id,
                    ContentBlock.block_key == "leadership_care_gallery"
                )
            )
        )
    )

    b = _get_or_create_block(
        session, "page", page_id, "leadership_care_gallery", lang_id,
        title="Ban Lãnh Đạo", block_type="gallery", sort_order=150,
    )
    for idx, (role, image_url, name) in enumerate(leadership_items):
        _get_or_create_item(
            session, b.id, f"leader_{idx + 1}",
            title=name,
            subtitle=role,
            sort_order=(idx + 1) * 10,
            metadata_json={"role": role, "image_url": image_url},
        )


def _seed_partner_blocks(session: Session, page_id: int, lang_id: int) -> None:
    # partner_categories
    b = _get_or_create_block(
        session, "page", page_id, "partner_categories", lang_id,
        title="Danh mục đối tác", block_type="tab_list", sort_order=160,
    )
    categories = [
        ("strategic_cooperation", "Hợp Tác Chiến Lược"),
        ("business_cooperation", "Hợp Tác Kinh Doanh"),
        ("institutional_cooperation", "Hợp Tác Tổ Chức"),
        ("industry_associations", "Hiệp Hội Ngành Nghề"),
    ]
    for idx, (key, label) in enumerate(categories):
        _get_or_create_item(
            session, b.id, key,
            title=label,
            sort_order=(idx + 1) * 10,
        )

    # partner_logos
    b = _get_or_create_block(
        session, "page", page_id, "partner_logos", lang_id,
        title="Logo đối tác", block_type="logo_grid", sort_order=170,
    )

    logos = [
        # Strategic Cooperation
        ("strategic_01", "http://www.shlinli.com/", _img("6370e615-d83c-43d2-ac61-da5d37ef3a23.jpg"), "strategic_cooperation"),
        ("strategic_02", "https://www.avic.com/", _img("b7dfe5e0-0484-44e2-8f1c-7ed1cf732672.jpg"), "strategic_cooperation"),
        ("strategic_03", "http://www.ntscid.com/", _img("b09df614-1954-45d7-9e72-2b943e91e032.jpg"), "strategic_cooperation"),
        ("strategic_04", "https://www.chinaso.com/", _img("bd7988af-2dda-4fc4-ba81-0aa2c46e1138.png"), "strategic_cooperation"),
        ("strategic_05", "https://www.bucg.com/", _img("5b360838-195b-417c-b9f5-c2729c6963b0.gif"), "strategic_cooperation"),
        ("strategic_06", "http://www.ccd.com.hk/", _img("5ef29600-187a-45e8-9990-5bc337249164.png"), "strategic_cooperation"),
        ("strategic_07", "http://www.hxwy.com.cn/", _img("79e2da0c-9570-4450-8766-303eb9d872c6.png"), "strategic_cooperation"),
        ("strategic_08", "https://www.az.com.cn/", _img("fd157699-2f31-43c8-a27d-f7bb51c050ca.png"), "strategic_cooperation"),
        ("strategic_09", "http://www.ideapool.tv/", _img("502cf951-2835-4ce4-97c7-e9dcc0b6cd87.png"), "strategic_cooperation"),
        ("strategic_10", "http://www.jiusi.net/", _img("2417ee26-0ef5-4c04-bc30-d8fdd9fc22f3.png"), "strategic_cooperation"),
        # Business Cooperation
        ("business_01", "http://www.10086.cn/bj/", _img("c07f7c3b-4b9c-49a7-add4-d6b7d5311c1e.png"), "business_cooperation"),
        ("business_02", "https://www.chd.com.cn/", _img("0829ee1d-40be-48bb-8add-3b20cc94f11f.png"), "business_cooperation"),
        ("business_03", "https://www.cnooc.com.cn/", _img("7bdcdf66-291d-48b7-8ad4-25b5e67ad981.png"), "business_cooperation"),
        ("business_04", "https://www.fosun.com/", _img("f144ac96-87d3-4a3d-b0fa-7e031dca7f5b.png"), "business_cooperation"),
        ("business_05", "http://www.cnpc.com.cn/", _img("58260315-6796-4d66-b84f-f655415b62fd.png"), "business_cooperation"),
        ("business_06", "http://www.cofco.com/cn/", _img("072c99df-dc7f-4363-9bec-272c60402238.png"), "business_cooperation"),
        ("business_07", "http://www.wanda.cn/", _img("4127f235-c134-4c81-96d8-356a23257058.png"), "business_cooperation"),
        ("business_08", "https://www.cfldcn.com/", _img("df21f2d8-be81-48da-899a-4cd1c087f94c.png"), "business_cooperation"),
        ("business_09", "http://www.spic.com.cn/", _img("5ecfab36-8675-40c8-a47e-84a3a4086d89.png"), "business_cooperation"),
        ("business_10", "https://www.gemdale.com/", _img("54310c5d-720a-4910-8d78-1662f39d508c.png"), "business_cooperation"),
        ("business_11", "https://www.sunac.com.cn/", _img("00ab262b-eacb-4eaf-9c94-af6f9c7cfd43.png"), "business_cooperation"),
        ("business_12", "http://www.bankofbeijing.com.cn", _img("bfd1c647-ea0d-4f7c-9eea-fdf1ff06c17f.png"), "business_cooperation"),
        ("business_13", "http://www.ccb.com/cn/home/indexv3.html", _img("ac28702e-28fd-4476-979b-70bc431bd038.png"), "business_cooperation"),
        ("business_14", "http://www.abchina.com/cn/", _img("86ed3568-8b26-4355-8738-a1606647c10d.png"), "business_cooperation"),
        ("business_15", "http://www.icbc.com.cn/icbc/", _img("c89e54dc-54d9-433b-86ea-12daedd33f46.png"), "business_cooperation"),
        # Institutional Cooperation
        ("institutional_01", "https://www.tsinghua.edu.cn/", _img("3967f2e4-4b28-4f06-8fed-d83b00787f43.png"), "institutional_cooperation"),
        ("institutional_02", "https://www.sg.pku.edu.cn/", _img("d89e4819-0071-4bf4-be69-3381c6027929.png"), "institutional_cooperation"),
        ("institutional_03", "http://www.buaa.edu.cn/", _img("f2325055-bddd-41df-a965-da871f0f78d7.png"), "institutional_cooperation"),
        ("institutional_04", "http://www.neu.edu.cn/", _img("fcc283b9-dd76-4103-84a0-602c1190eba4.png"), "institutional_cooperation"),
        ("institutional_05", "https://www.yzjsxy.com/", _img("5b670d41-92f8-44db-947b-78944ebcc82a.png"), "institutional_cooperation"),
        # Industry Associations
        ("association_01", "http://www.cida.org.cn/", _img("adb7b287-e16d-447b-a130-4bafc4b1d371.png"), "industry_associations"),
        ("association_02", "http://www.cbda.cn/", _img("a93c78ed-bb1f-4f89-94d4-ddb8cb1cbbfe.gif"), "industry_associations"),
        ("association_03", "https://www.chinamuseum.org.cn/", _img("57325a61-ee56-490a-b89c-90e2c56f647e.png"), "industry_associations"),
        ("association_04", "http://www.bcda.org.cn/", _img("9ee5b030-ea8b-4887-9244-186dd43a50ef.png"), "industry_associations"),
        ("association_05", "http://www.caec.org.cn/", _img("8ee0eaaf-d284-4cdc-914b-8c77f7732e49.png"), "industry_associations"),
        ("association_06", "http://www.jszszx.com.cn/", _img("339748f8-51e2-4090-8873-2ebb97fa0c29.png"), "industry_associations"),
    ]

    for idx, (item_key, website, image_url, category) in enumerate(logos):
        _get_or_create_item(
            session, b.id, item_key,
            title=None,
            link=website,
            sort_order=(idx + 1) * 10,
            metadata_json={"category": category, "image_url": image_url, "website": website},
        )
