from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from sqlalchemy import delete, select

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.db.session import SessionLocal
from app.models.content import ContentBlock, ContentBlockItem, Page
from app.models.media import MediaAsset  # noqa: F401


LEGACY_BLOCK_KEYS = {
    "hero_nav",
    "culture_purpose",
    "culture_mission",
    "culture_spirit",
    "partner_categories",
    "partner_logos",
}

ALLOWED_ITEM_KEY_PATTERNS: dict[str, re.Pattern[str]] = {
    "hero_summary": re.compile(r"^(headline|description|cover_image)$"),
    "intro_media": re.compile(r"^cover_image$"),
    "intro_video": re.compile(r"^(video_button|video_url)$"),
    "intro_paragraphs": re.compile(r"^paragraph_\d+$"),
    "speech_profile": re.compile(r"^portrait$"),
    "speech_body": re.compile(r"^(vision|mission)$"),
    "speech_signature": re.compile(r"^(sign_title|sign_name|signature_image)$"),
    "org_chart_image": re.compile(r"^main_chart$"),
    "culture_values": re.compile(r"^value_\d+$"),
    "timeline": re.compile(r"^milestone_\d+$"),
    "leadership_care_gallery": re.compile(r"^leader_\d+$"),
}


def _display_title(block_key: str, item_key: str) -> str | None:
    block_key = str(block_key or "").strip().lower()
    item_key = str(item_key or "").strip().lower()

    if block_key == "hero_summary":
        if item_key == "headline":
            return "Page 1 Hero - Tieu de"
        if item_key == "description":
            return "Page 1 Hero - Noi dung chi tiet / Van ban"
        if item_key == "cover_image":
            return "Page 1 Hero - Hinh anh"

    if block_key == "intro_media" and item_key == "cover_image":
        return "Page 2 Gioi thieu cong ty - Hinh anh"

    if block_key == "intro_paragraphs":
        matched = re.match(r"^paragraph_(\d+)$", item_key)
        if matched:
            return f"Page 2 Gioi thieu cong ty - Noi dung chi tiet / Van ban {matched.group(1)}"

    return None


def run() -> dict[str, int | str]:
    with SessionLocal() as session:
        about_page = session.scalar(select(Page).where(Page.slug == "about"))
        if not about_page:
            raise RuntimeError("Page slug='about' not found.")

        block_rows = session.scalars(
            select(ContentBlock).where(
                ContentBlock.entity_type == "page",
                ContentBlock.entity_id == about_page.id,
            )
        ).all()

        legacy_block_ids = [row.id for row in block_rows if (row.block_key or "") in LEGACY_BLOCK_KEYS]

        deleted_legacy_blocks = 0
        deleted_legacy_items = 0
        if legacy_block_ids:
            deleted_legacy_items = session.query(ContentBlockItem).filter(
                ContentBlockItem.block_id.in_(legacy_block_ids)
            ).count()
            session.execute(delete(ContentBlockItem).where(ContentBlockItem.block_id.in_(legacy_block_ids)))

            deleted_legacy_blocks = session.query(ContentBlock).filter(
                ContentBlock.id.in_(legacy_block_ids)
            ).count()
            session.execute(delete(ContentBlock).where(ContentBlock.id.in_(legacy_block_ids)))
            session.flush()

        block_rows = session.scalars(
            select(ContentBlock).where(
                ContentBlock.entity_type == "page",
                ContentBlock.entity_id == about_page.id,
            )
        ).all()

        deleted_invalid_items = 0
        retitled_items = 0

        for block in block_rows:
            block_key = str(block.block_key or "").strip()
            pattern = ALLOWED_ITEM_KEY_PATTERNS.get(block_key)
            items = session.scalars(
                select(ContentBlockItem).where(ContentBlockItem.block_id == block.id)
            ).all()

            if pattern:
                invalid_ids = [
                    item.id
                    for item in items
                    if not pattern.match(str(item.item_key or "").strip())
                ]
                if invalid_ids:
                    deleted_invalid_items += len(invalid_ids)
                    session.execute(delete(ContentBlockItem).where(ContentBlockItem.id.in_(invalid_ids)))
                    items = [item for item in items if item.id not in invalid_ids]

            for item in items:
                new_title = _display_title(block_key, str(item.item_key or ""))
                if new_title and (item.title or "") != new_title:
                    item.title = new_title
                    retitled_items += 1

        session.commit()

        return {
            "about_page_id": about_page.id,
            "deleted_legacy_blocks": deleted_legacy_blocks,
            "deleted_legacy_items": deleted_legacy_items,
            "deleted_invalid_items": deleted_invalid_items,
            "retitled_items": retitled_items,
        }


if __name__ == "__main__":
    report = run()
    print(json.dumps(report, ensure_ascii=True, indent=2))
