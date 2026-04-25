from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from pathlib import Path
import re
import sys
import unicodedata

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.media import MediaAsset
from app.models.products import Product, ProductImage
from app.models.projects import ProjectProduct  # noqa: F401


DEFAULT_MEDIA_IDS = [4, 5, 6, 7]
DEFAULT_JSON_OUTPUT = PROJECT_ROOT / "scripts" / "reports" / "media_id_4_5_6_7_mapping_audit.json"
DEFAULT_MD_OUTPUT = PROJECT_ROOT / "scripts" / "reports" / "media_id_4_5_6_7_mapping_audit.md"


@dataclass
class CandidateProduct:
    product_id: int
    slug: str | None
    sku: str | None
    name: str | None
    score: float
    reasons: list[str]
    current_image_url: str | None
    matching_gallery_image_ids: list[int]



def slugify(value: str | None) -> str:
    raw = str(value or "").strip().lower()
    raw = raw.replace("đ", "d")
    raw = unicodedata.normalize("NFD", raw)
    raw = "".join(char for char in raw if unicodedata.category(char) != "Mn")
    raw = re.sub(r"[^a-z0-9]+", "-", raw)
    return raw.strip("-")



def normalize_text(value: str | None) -> str:
    return slugify(value)



def extract_storage_leaf(storage_path: str | None) -> str:
    normalized = str(storage_path or "").strip().strip("/")
    if not normalized:
        return ""
    return normalized.split("/")[-1]



def filename_stem(file_name: str | None) -> str:
    return slugify(Path(str(file_name or "").strip()).stem)



def similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()



def build_candidate_products(media: MediaAsset, products: list[Product], gallery_by_product: dict[int, list[ProductImage]]) -> list[CandidateProduct]:
    media_title = normalize_text(media.title)
    media_file = filename_stem(media.file_name)
    storage_leaf = slugify(extract_storage_leaf(media.storage_path))
    current_url = str(media.url or "").strip()

    candidates: list[CandidateProduct] = []
    for product in products:
        score = 0.0
        reasons: list[str] = []
        product_slug = slugify(product.slug)
        product_name = normalize_text(product.name)
        product_sku = slugify(product.sku)
        gallery_items = gallery_by_product.get(product.id, [])
        matching_gallery = [image.id for image in gallery_items if str(image.url or "").strip() == current_url]

        if current_url and str(product.image_url or "").strip() == current_url:
            score += 100
            reasons.append("Exact match với products.image_url")

        if matching_gallery:
            score += 90
            reasons.append(f"Exact match với product_images.url ({len(matching_gallery)})")

        if media_title and media_title == product_name:
            score += 55
            reasons.append("Title media trùng tên sản phẩm")
        else:
            title_name_similarity = similarity(media_title, product_name)
            if title_name_similarity >= 0.7:
                score += round(title_name_similarity * 40, 2)
                reasons.append(f"Title gần giống tên sản phẩm ({title_name_similarity:.2f})")

        if storage_leaf and storage_leaf == product_slug:
            score += 50
            reasons.append("storage_path leaf trùng slug sản phẩm")
        else:
            storage_slug_similarity = similarity(storage_leaf, product_slug)
            if storage_slug_similarity >= 0.7:
                score += round(storage_slug_similarity * 35, 2)
                reasons.append(f"storage_path gần giống slug ({storage_slug_similarity:.2f})")

        if media_file and product_sku and product_sku in media_file:
            score += 35
            reasons.append("Tên file chứa SKU sản phẩm")

        if media_file and product_slug and similarity(media_file, product_slug) >= 0.7:
            score += round(similarity(media_file, product_slug) * 25, 2)
            reasons.append("Tên file gần giống slug sản phẩm")

        if score > 0:
            candidates.append(
                CandidateProduct(
                    product_id=product.id,
                    slug=product.slug,
                    sku=product.sku,
                    name=product.name,
                    score=round(score, 2),
                    reasons=reasons,
                    current_image_url=product.image_url,
                    matching_gallery_image_ids=matching_gallery,
                )
            )

    candidates.sort(key=lambda item: (-item.score, item.product_id))
    return candidates[:10]



def inspect_orphan_gallery_rows(session, media: MediaAsset) -> list[dict]:
    current_url = str(media.url or "").strip()
    rows = session.scalars(select(ProductImage).where(ProductImage.url == current_url)).all()
    results = []
    for row in rows:
        parent = session.get(Product, row.product_id)
        results.append(
            {
                "product_image_id": row.id,
                "product_id": row.product_id,
                "sort_order": row.sort_order,
                "alt": row.alt,
                "product_exists": bool(parent),
                "product_slug": getattr(parent, "slug", None),
                "product_name": getattr(parent, "name", None),
                "product_sku": getattr(parent, "sku", None),
            }
        )
    return results



def build_report(media_ids: list[int]) -> dict:
    with SessionLocal() as session:
        media_assets = session.scalars(
            select(MediaAsset).where(MediaAsset.id.in_(media_ids)).order_by(MediaAsset.id)
        ).all()
        all_products = session.scalars(select(Product).order_by(Product.id)).all()
        all_gallery = session.scalars(select(ProductImage).order_by(ProductImage.id)).all()

        gallery_by_product: dict[int, list[ProductImage]] = {}
        for image in all_gallery:
            gallery_by_product.setdefault(image.product_id, []).append(image)

        entries = []
        for media in media_assets:
            orphan_gallery_rows = inspect_orphan_gallery_rows(session, media)
            direct_products = session.scalars(
                select(Product).where(Product.image_url == media.url)
            ).all()
            candidates = build_candidate_products(media, all_products, gallery_by_product)
            best_candidate = candidates[0] if candidates else None

            recommendation = {
                "action": "manual_review",
                "target_product_id": None,
                "target_product_slug": None,
                "confidence": "low",
                "notes": [],
            }

            if best_candidate and best_candidate.score >= 100:
                recommendation = {
                    "action": "map_to_existing_product",
                    "target_product_id": best_candidate.product_id,
                    "target_product_slug": best_candidate.slug,
                    "confidence": "high",
                    "notes": ["Có exact match trực tiếp theo URL hoặc điểm số rất cao."],
                }
            elif best_candidate and best_candidate.score >= 60:
                recommendation = {
                    "action": "likely_map_to_product",
                    "target_product_id": best_candidate.product_id,
                    "target_product_slug": best_candidate.slug,
                    "confidence": "medium",
                    "notes": ["Ứng viên mạnh nhất có độ tương đồng cao, nhưng nên review trước khi migrate."],
                }

            if orphan_gallery_rows and any(not row["product_exists"] for row in orphan_gallery_rows):
                recommendation["notes"].append("Phát hiện product_images trỏ tới product_id mồ côi; cần xử lý lại mapping gallery.")

            entries.append(
                {
                    "media": {
                        "id": media.id,
                        "title": media.title,
                        "file_name": media.file_name,
                        "url": media.url,
                        "storage_path": media.storage_path,
                        "storage_leaf": extract_storage_leaf(media.storage_path),
                    },
                    "direct_product_image_url_matches": [
                        {
                            "product_id": product.id,
                            "slug": product.slug,
                            "sku": product.sku,
                            "name": product.name,
                        }
                        for product in direct_products
                    ],
                    "gallery_url_matches": orphan_gallery_rows,
                    "candidate_products": [asdict(candidate) for candidate in candidates],
                    "recommendation": recommendation,
                }
            )

    return {
        "summary": {
            "media_ids": media_ids,
            "checked_count": len(entries),
        },
        "entries": entries,
    }



def render_markdown(report: dict) -> str:
    lines = [
        "# Đối chiếu mapping cho media_id 4,5,6,7",
        "",
        "## Tóm tắt",
        "",
        f"- Media IDs kiểm tra: `{', '.join(str(item) for item in report['summary']['media_ids'])}`",
        f"- Số media tìm thấy: **{report['summary']['checked_count']}**",
        "",
        "## Chi tiết",
        "",
    ]

    for entry in report["entries"]:
        media = entry["media"]
        recommendation = entry["recommendation"]
        lines.extend(
            [
                f"### media_id {media['id']} — {media['title'] or media['file_name'] or '-'}",
                "",
                f"- URL hiện tại: `{media['url']}`",
                f"- storage_path: `{media['storage_path']}`",
                f"- storage leaf: `{media['storage_leaf']}`",
                f"- Đề xuất: **{recommendation['action']}**",
                f"- Product đích đề xuất: `{recommendation['target_product_id']}` / `{recommendation['target_product_slug']}`",
                f"- Độ tin cậy: **{recommendation['confidence']}**",
                "",
            ]
        )

        if recommendation["notes"]:
            lines.append("- Ghi chú:")
            for note in recommendation["notes"]:
                lines.append(f"  - {note}")
            lines.append("")

        direct_matches = entry["direct_product_image_url_matches"]
        lines.append("- Direct matches từ products.image_url:")
        if direct_matches:
            for item in direct_matches:
                lines.append(
                    f"  - Product #{item['product_id']} / slug=`{item['slug']}` / sku=`{item['sku']}` / name=`{item['name']}`"
                )
        else:
            lines.append("  - Không có")
        lines.append("")

        gallery_matches = entry["gallery_url_matches"]
        lines.append("- Matches từ product_images.url:")
        if gallery_matches:
            for item in gallery_matches:
                lines.append(
                    f"  - product_image #{item['product_image_id']} / product_id={item['product_id']} / product_exists={item['product_exists']} / slug=`{item['product_slug']}` / sort_order={item['sort_order']}"
                )
        else:
            lines.append("  - Không có")
        lines.append("")

        lines.append("- Top candidate products:")
        if entry["candidate_products"]:
            for candidate in entry["candidate_products"][:5]:
                reasons = "; ".join(candidate["reasons"])
                lines.append(
                    f"  - Product #{candidate['product_id']} / slug=`{candidate['slug']}` / sku=`{candidate['sku']}` / score={candidate['score']} / reasons={reasons}"
                )
        else:
            lines.append("  - Không có candidate")
        lines.append("")

    return "\n".join(lines)



def main() -> None:
    parser = argparse.ArgumentParser(description="Audit mapping riêng cho nhóm media_id 4,5,6,7")
    parser.add_argument("--media-ids", default=",".join(str(item) for item in DEFAULT_MEDIA_IDS))
    parser.add_argument("--json-output", default=str(DEFAULT_JSON_OUTPUT))
    parser.add_argument("--md-output", default=str(DEFAULT_MD_OUTPUT))
    args = parser.parse_args()

    media_ids = [int(item.strip()) for item in str(args.media_ids).split(",") if item.strip()]
    report = build_report(media_ids)

    json_output = Path(args.json_output)
    md_output = Path(args.md_output)
    json_output.parent.mkdir(parents=True, exist_ok=True)
    md_output.parent.mkdir(parents=True, exist_ok=True)
    json_output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_output.write_text(render_markdown(report), encoding="utf-8")

    print(f"[OK] JSON audit: {json_output}")
    print(f"[OK] Markdown audit: {md_output}")
    print(f"[SUMMARY] checked={report['summary']['checked_count']}")


if __name__ == "__main__":
    main()
