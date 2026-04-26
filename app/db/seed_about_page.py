"""
Sprint 2 - Seed About page CMS data.

Tạo 1 page canonical slug="about" với đầy đủ:
- 7 page_sections
- các content_blocks cho Page 1 -> Page 7
- dữ liệu idempotent, chạy lại không tạo duplicate
"""

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.models.content import ContentBlock, ContentBlockItem, Page, PageSection


# ---------------------------------------------------------------------------
# Helpers - idempotent get-or-create
# ---------------------------------------------------------------------------

def _get_or_create_page(session: Session, slug: str, language_id: int, **kwargs) -> Page:
  page = session.scalar(select(Page).where(Page.slug == slug, Page.language_id == language_id))
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
    filters.append(or_(ContentBlock.language_id == language_id, ContentBlock.language_id.is_(None)))
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


def _img(file_name: str) -> str:
  return f"{_IMG_BASE}/{file_name}"


def _repo(file_name: str) -> str:
  return f"{_REPO_BASE}/{file_name}"


# ---------------------------------------------------------------------------
# Cleanup legacy about data
# ---------------------------------------------------------------------------

def _cleanup_legacy_about_blocks(session: Session, page_id: int) -> None:
  legacy_block_keys = [
    "hero_nav",
    "culture_purpose",
    "culture_mission",
    "culture_spirit",
    "partner_categories",
    "partner_logos",
  ]
  legacy_section_anchors = ["cooperative_partner"]

  legacy_block_ids = session.scalars(
    select(ContentBlock.id).where(
      ContentBlock.entity_type == "page",
      ContentBlock.entity_id == page_id,
      ContentBlock.block_key.in_(legacy_block_keys),
    )
  ).all()

  if legacy_block_ids:
    session.execute(delete(ContentBlockItem).where(ContentBlockItem.block_id.in_(legacy_block_ids)))
    session.execute(delete(ContentBlock).where(ContentBlock.id.in_(legacy_block_ids)))

  session.execute(
    delete(PageSection).where(
      PageSection.page_id == page_id,
      PageSection.anchor.in_(legacy_section_anchors),
    )
  )
  session.flush()


# ---------------------------------------------------------------------------
# Main seed function
# ---------------------------------------------------------------------------

def seed_about_page(session: Session, language_id: int) -> None:
  """Seed About page with sections, blocks, and items."""

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
  page_id = about.id

  _cleanup_legacy_about_blocks(session, page_id)

  sections_seed = [
    ("hero", "Giới Thiệu Thiên Đồng", "hero", 10),
    ("company_introduction", "Về Chúng Tôi", "content", 20),
    ("chairman_speech", "Tầm Nhìn & Chiến Lược", "content", 30),
    ("organization_chart", "Sơ Đồ Tổ Chức", "media", 40),
    ("corporate_culture", "Văn Hóa Doanh Nghiệp", "content", 50),
    ("development_course", "Lịch Sử Phát Triển", "timeline", 60),
    ("leadership_care", "Ban Lãnh Đạo", "gallery", 70),
  ]

  for anchor, title, section_type, sort_order in sections_seed:
    _get_or_create_section(
      session,
      page_id=page_id,
      anchor=anchor,
      title=title,
      section_type=section_type,
      sort_order=sort_order,
      content=None,
      image_id=None,
    )

  _seed_hero_blocks(session, page_id, language_id)
  _seed_intro_blocks(session, page_id, language_id)
  _seed_speech_blocks(session, page_id, language_id)
  _seed_org_chart_blocks(session, page_id, language_id)
  _seed_culture_blocks(session, page_id, language_id)
  _seed_timeline_blocks(session, page_id, language_id)
  _seed_leadership_blocks(session, page_id, language_id)


# ---------------------------------------------------------------------------
# Seeders per section
# ---------------------------------------------------------------------------

def _seed_hero_blocks(session: Session, page_id: int, lang_id: int) -> None:
  block = _get_or_create_block(
    session,
    "page",
    page_id,
    "hero_summary",
    lang_id,
    title="Tổng quan giới thiệu",
    block_type="key_value",
    sort_order=10,
  )
  _get_or_create_item(session, block.id, "headline", title="Page 1 Hero - Tieu de", sort_order=10)
  _get_or_create_item(
    session,
    block.id,
    "description",
    title="Page 1 Hero - Noi dung chi tiet / Van ban",
    content="Thiên Đồng Việt Nam - Uy tín từ những điều nhỏ nhất. Chuyên cung cấp các dòng đá mềm và tấm ốp tường linh hoạt cho không gian hiện đại.",
    sort_order=20,
  )
  _get_or_create_item(
    session,
    block.id,
    "cover_image",
    title="Page 1 Hero - Hinh anh",
    metadata_json={"src": "/images/banner/banner3.jpg"},
    sort_order=30,
  )


def _seed_intro_blocks(session: Session, page_id: int, lang_id: int) -> None:
  block = _get_or_create_block(
    session,
    "page",
    page_id,
    "intro_media",
    lang_id,
    title="Giới thiệu công ty",
    block_type="media",
    sort_order=30,
  )
  _get_or_create_item(
    session,
    block.id,
    "cover_image",
    title="Page 2 Gioi thieu cong ty - Hinh anh",
    sort_order=10,
    metadata_json={
      "src": "https://res.cloudinary.com/db1b15yn4/image/upload/v1776357180/China_web/banner/homepage-banner-05-image.jpg",
      "legacy_source_url": _img("f1225086-4996-4f1d-886-08f4228a378e.png"),
    },
  )

  block = _get_or_create_block(
    session,
    "page",
    page_id,
    "intro_video",
    lang_id,
    title="Company Introduction Video",
    block_type="video",
    sort_order=40,
  )
  _get_or_create_item(session, block.id, "video_button", title="VIDEO +", sort_order=10)
  _get_or_create_item(
    session,
    block.id,
    "video_url",
    title="Company intro video",
    link="/images/vd/1fb59345-a995-4408-b03b-e8e38ff258e7.web.mp4",
    metadata_json={
      "external_source_url": "https://drive.google.com/file/d/120045rHguHlBfZHH2UnwY58KL8DAUhZv/view?usp=sharing",
      "media_migration_status": "pending",
    },
    sort_order=20,
  )

  paragraphs = [
    "CÔNG TY TNHH THƯƠNG MẠI QUỐC TẾ THIÊN ĐỒNG VIỆT NAM chuyên cung cấp các dòng đá mềm – tấm ốp linh hoạt cao cấp, ứng dụng trong trang trí nội thất và ngoại thất hiện đại.",
    "Sản phẩm của chúng tôi mang lại giải pháp thay thế hoàn hảo cho đá tự nhiên truyền thống với ưu điểm nhẹ, linh hoạt, dễ thi công và tiết kiệm chi phí, phù hợp cho nhiều loại công trình từ nhà ở, showroom đến dự án thương mại.",
  ]
  block = _get_or_create_block(
    session,
    "page",
    page_id,
    "intro_paragraphs",
    lang_id,
    title="Nội dung giới thiệu (Các đoạn văn)",
    block_type="rich_text_list",
    sort_order=50,
  )
  session.execute(delete(ContentBlockItem).where(ContentBlockItem.block_id == block.id))
  for idx, text in enumerate(paragraphs, start=1):
    _get_or_create_item(
      session,
      block.id,
      f"paragraph_{idx}",
      title=f"Page 2 Gioi thieu cong ty - Noi dung chi tiet / Van ban {idx}",
      content=text,
      sort_order=idx * 10,
    )


def _seed_speech_blocks(session: Session, page_id: int, lang_id: int) -> None:
  block = _get_or_create_block(
    session,
    "page",
    page_id,
    "speech_profile",
    lang_id,
    title="Tầm Nhìn & Sứ Mệnh",
    block_type="media",
    sort_order=60,
  )
  _get_or_create_item(
    session,
    block.id,
    "portrait",
    title="Hình ảnh Giám đốc",
    sort_order=10,
    metadata_json={"src": "https://res.cloudinary.com/db1b15yn4/image/upload/v1776694034/Image_20260418142413_9_3_m65uzj.jpg"},
  )

  vision = (
    "Trở thành đơn vị tiên phong tại Việt Nam trong lĩnh vực cung cấp vật liệu trang trí linh hoạt, "
    "đặc biệt là đá mềm, hướng đến thị trường quốc tế."
  )
  mission = (
    "Mang đến giải pháp vật liệu ốp lát hiện đại, bền đẹp và tối ưu chi phí, "
    "giúp khách hàng nâng tầm không gian sống và công trình xây dựng."
  )

  block = _get_or_create_block(
    session,
    "page",
    page_id,
    "speech_body",
    lang_id,
    title="Tầm Nhìn & Sứ Mệnh",
    block_type="rich_text_list",
    sort_order=70,
  )
  session.execute(delete(ContentBlockItem).where(ContentBlockItem.block_id == block.id))
  _get_or_create_item(session, block.id, "vision", title="Tầm nhìn", content=vision, sort_order=10)
  _get_or_create_item(session, block.id, "mission", title="Sứ mệnh", content=mission, sort_order=20)

  block = _get_or_create_block(
    session,
    "page",
    page_id,
    "speech_signature",
    lang_id,
    title="Chairman Signature",
    block_type="key_value",
    sort_order=80,
  )
  _get_or_create_item(session, block.id, "sign_title", title="", sort_order=10)
  _get_or_create_item(session, block.id, "sign_name", title="", sort_order=20)


def _seed_org_chart_blocks(session: Session, page_id: int, lang_id: int) -> None:
  block = _get_or_create_block(
    session,
    "page",
    page_id,
    "org_chart_image",
    lang_id,
    title="Sơ Đồ Tổ Chức",
    block_type="media",
    sort_order=90,
  )
  _get_or_create_item(
    session,
    block.id,
    "main_chart",
    title="Organization chart image",
    sort_order=10,
    metadata_json={
      "src": _img("bcb4ff12-813e-43ef-9669-e5ed2da9a123.png"),
      "org_chart_text": "Giám đốc | Phòng Kinh doanh | Phòng Marketing | Phòng Kỹ thuật / Thi công | Kế toán – Hành chính",
    },
  )


def _seed_culture_blocks(session: Session, page_id: int, lang_id: int) -> None:
  culture_data = [
    (
      "culture_values",
      "Giá trị cốt lõi",
      130,
      [
        ("Chất lượng", "Sản phẩm đạt tiêu chuẩn cao"),
        ("Uy tín", "Cam kết đúng tiến độ, đúng chất lượng"),
        ("Đổi mới", "Luôn cập nhật xu hướng vật liệu mới"),
        ("Khách hàng là trung tâm", "Đặt nhu cầu khách hàng lên hàng đầu"),
        ("Hợp tác lâu dài", "Phát triển bền vững cùng đối tác"),
      ],
    ),
  ]

  culture_keys = ["culture_purpose", "culture_mission", "culture_spirit", "culture_values"]
  session.execute(
    delete(ContentBlockItem).where(
      ContentBlockItem.block_id.in_(
        select(ContentBlock.id).where(
          ContentBlock.entity_type == "page",
          ContentBlock.entity_id == page_id,
          ContentBlock.block_key.in_(culture_keys),
        )
      )
    )
  )
  session.execute(
    delete(ContentBlock).where(
      ContentBlock.entity_type == "page",
      ContentBlock.entity_id == page_id,
      ContentBlock.block_key.in_(culture_keys),
    )
  )
  session.flush()

  for block_key, block_title, sort_order, items in culture_data:
    block = _get_or_create_block(
      session,
      "page",
      page_id,
      block_key,
      lang_id,
      title=block_title,
      block_type="bullet_list",
      sort_order=sort_order,
    )
    for idx, (label, text) in enumerate(items, start=1):
      _get_or_create_item(
        session,
        block.id,
        f"value_{idx}",
        title=label,
        content=text,
        sort_order=idx * 10,
      )


def _seed_timeline_blocks(session: Session, page_id: int, lang_id: int) -> None:
  timeline_entries = [
    ("2024", "", "Thành lập công ty tại Bình Dương", ""),
    ("2024 - nay", "", "Phát triển và phân phối sản phẩm đá mềm, mở rộng mạng lưới khách hàng trong và ngoài nước", ""),
  ]

  block = _get_or_create_block(
    session,
    "page",
    page_id,
    "timeline",
    lang_id,
    title="Lịch Sử Phát Triển",
    block_type="timeline",
    sort_order=140,
  )
  session.execute(delete(ContentBlockItem).where(ContentBlockItem.block_id == block.id))

  for idx, (year, month, title, image_url) in enumerate(timeline_entries, start=1):
    metadata = {"year": year, "month": month}
    if image_url:
      metadata["image_url"] = image_url
    _get_or_create_item(
      session,
      block.id,
      f"milestone_{idx}",
      title=title,
      sort_order=idx * 10,
      metadata_json=metadata,
    )


def _seed_leadership_blocks(session: Session, page_id: int, lang_id: int) -> None:
  leadership_items = [
    (
      "Giám đốc",
      "https://res.cloudinary.com/db1b15yn4/image/upload/v1776694034/Image_20260418142413_9_3_m65uzj.jpg",
      "Nguyễn Hà Thanh",
    ),
  ]

  session.execute(
    delete(ContentBlockItem).where(
      ContentBlockItem.block_id.in_(
        select(ContentBlock.id).where(
          ContentBlock.entity_type == "page",
          ContentBlock.entity_id == page_id,
          ContentBlock.block_key == "leadership_care_gallery",
        )
      )
    )
  )

  block = _get_or_create_block(
    session,
    "page",
    page_id,
    "leadership_care_gallery",
    lang_id,
    title="Ban Lãnh Đạo",
    block_type="gallery",
    sort_order=150,
  )
  for idx, (role, image_url, name) in enumerate(leadership_items, start=1):
    _get_or_create_item(
      session,
      block.id,
      f"leader_{idx}",
      title=name,
      subtitle=role,
      sort_order=idx * 10,
      metadata_json={"role": role, "image_url": image_url},
    )
