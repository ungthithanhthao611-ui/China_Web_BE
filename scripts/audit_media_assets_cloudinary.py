from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.media import MediaAsset
from app.models.products import Product, ProductImage
from app.models.projects import ProjectProduct  # noqa: F401


DEFAULT_EXPECTED_ROOT = "China_web"
DEFAULT_PRODUCTS_FOLDER = "products"
DEFAULT_JSON_OUTPUT = PROJECT_ROOT / "scripts" / "reports" / "media_assets_cloudinary_audit.json"
DEFAULT_MD_OUTPUT = PROJECT_ROOT / "scripts" / "reports" / "media_assets_cloudinary_audit.md"


@dataclass
class AuditEntry:
    media_id: int
    title: str | None
    file_name: str | None
    url: str
    storage_path: str | None
    actual_folder: str
    expected_folder: str | None
    reasons: list[str]
    linked_products: list[dict[str, str | int | None]]



def normalize_path(value: str | None) -> str:
    return "/".join(segment for segment in str(value or "").strip().strip("/").split("/") if segment)



def is_cloudinary_asset(record: MediaAsset) -> bool:
    url = str(record.url or "")
    storage_path = str(record.storage_path or "")
    return "res.cloudinary.com/" in url or bool(storage_path)



def expected_product_folder(root_folder: str, products_folder: str, slug: str | None) -> str:
    normalized_slug = normalize_path(slug)
    base = normalize_path(f"{root_folder}/{products_folder}")
    return f"{base}/{normalized_slug}" if normalized_slug else base



def build_product_media_index(db: Session) -> dict[str, list[dict[str, str | int | None]]]:
    index: dict[str, list[dict[str, str | int | None]]] = defaultdict(list)

    products = db.scalars(select(Product)).all()
    for product in products:
        product_payload = {
            "product_id": product.id,
            "slug": product.slug,
            "sku": product.sku,
            "name": product.name,
            "source": "products.image_url",
        }
        normalized_main_url = str(product.image_url or "").strip()
        if normalized_main_url:
            index[normalized_main_url].append(product_payload)

    product_images = db.scalars(select(ProductImage)).all()
    products_by_id = {product.id: product for product in products}
    for image in product_images:
        parent = products_by_id.get(image.product_id)
        payload = {
            "product_id": image.product_id,
            "slug": getattr(parent, "slug", None),
            "sku": getattr(parent, "sku", None),
            "name": getattr(parent, "name", None),
            "source": "product_images.url",
        }
        normalized_gallery_url = str(image.url or "").strip()
        if normalized_gallery_url:
            index[normalized_gallery_url].append(payload)

    return index



def audit_media_assets(db: Session, expected_root: str, products_folder: str) -> dict[str, object]:
    media_assets = db.scalars(select(MediaAsset).order_by(MediaAsset.id)).all()
    product_index = build_product_media_index(db)

    mismatches: list[AuditEntry] = []
    stats = Counter()

    expected_root_normalized = normalize_path(expected_root)
    expected_root_lower = expected_root_normalized.lower()
    products_folder_normalized = normalize_path(products_folder)
    products_folder_lower = products_folder_normalized.lower()

    for media in media_assets:
        stats["total_media_assets"] += 1
        if not is_cloudinary_asset(media):
            stats["non_cloudinary_assets"] += 1
            continue

        stats["cloudinary_assets"] += 1
        storage_path = normalize_path(media.storage_path)
        path_parts = storage_path.split("/") if storage_path else []
        linked_products = product_index.get(str(media.url or "").strip(), [])
        reasons: list[str] = []
        expected_folder: str | None = None

        if not storage_path:
            reasons.append("missing_storage_path")
        else:
            actual_root = path_parts[0] if path_parts else ""
            if actual_root.lower() != expected_root_lower:
                reasons.append("wrong_root_folder")
            elif actual_root != expected_root_normalized:
                reasons.append("root_folder_casing_mismatch")

        if linked_products:
            stats["product_linked_assets"] += 1
            primary_product = linked_products[0]
            expected_folder = expected_product_folder(
                expected_root_normalized,
                products_folder_normalized,
                str(primary_product.get("slug") or ""),
            )
            expected_prefix_lower = expected_folder.lower()
            actual_folder = storage_path.lower()

            if not actual_folder.startswith(expected_prefix_lower):
                reasons.append("product_folder_mismatch")
            else:
                expected_parts = expected_folder.split("/")
                if len(path_parts) >= 2:
                    actual_products_folder = path_parts[1]
                    if actual_products_folder.lower() != products_folder_lower:
                        reasons.append("wrong_products_folder_name")
                    elif actual_products_folder != products_folder_normalized:
                        reasons.append("products_folder_casing_mismatch")
                for idx, expected_part in enumerate(expected_parts[: len(path_parts)]):
                    if idx < len(path_parts) and path_parts[idx].lower() == expected_part.lower() and path_parts[idx] != expected_part:
                        if idx == 2:
                            reasons.append("product_slug_casing_mismatch")
        else:
            stats["unlinked_cloudinary_assets"] += 1

        if reasons:
            stats["mismatched_assets"] += 1
            mismatches.append(
                AuditEntry(
                    media_id=media.id,
                    title=media.title,
                    file_name=media.file_name,
                    url=str(media.url or ""),
                    storage_path=media.storage_path,
                    actual_folder=storage_path,
                    expected_folder=expected_folder,
                    reasons=sorted(set(reasons)),
                    linked_products=linked_products,
                )
            )

    return {
        "summary": {
            **dict(stats),
            "expected_root": expected_root_normalized,
            "expected_products_folder": products_folder_normalized,
        },
        "mismatches": [asdict(entry) for entry in mismatches],
    }



def render_markdown(report: dict[str, object]) -> str:
    summary = report["summary"]
    mismatches = report["mismatches"]
    lines = [
        "# Audit media_assets Cloudinary",
        "",
        "## Tóm tắt",
        "",
        f"- Tổng media_assets: **{summary.get('total_media_assets', 0)}**",
        f"- Cloudinary assets: **{summary.get('cloudinary_assets', 0)}**",
        f"- Non-Cloudinary assets: **{summary.get('non_cloudinary_assets', 0)}**",
        f"- Product-linked assets: **{summary.get('product_linked_assets', 0)}**",
        f"- Unlinked Cloudinary assets: **{summary.get('unlinked_cloudinary_assets', 0)}**",
        f"- Mismatched assets: **{summary.get('mismatched_assets', 0)}**",
        f"- Chuẩn root mong muốn: `{summary.get('expected_root', '')}`",
        f"- Chuẩn thư mục sản phẩm: `{summary.get('expected_products_folder', '')}`",
        "",
        "## Danh sách asset sai chuẩn",
        "",
    ]

    if not mismatches:
        lines.append("Không phát hiện asset Cloudinary nào sai chuẩn.")
        return "\n".join(lines)

    lines.extend(
        [
            "| media_id | title | storage_path | expected_folder | reasons | linked_products |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )

    for item in mismatches:
        linked_products = ", ".join(
            f"#{product.get('product_id')}:{product.get('slug') or '-'} ({product.get('source')})"
            for product in item.get("linked_products", [])
        )
        lines.append(
            "| {media_id} | {title} | {storage_path} | {expected_folder} | {reasons} | {linked_products} |".format(
                media_id=item.get("media_id", ""),
                title=str(item.get("title") or item.get("file_name") or "").replace("|", "\\|"),
                storage_path=str(item.get("storage_path") or "").replace("|", "\\|"),
                expected_folder=str(item.get("expected_folder") or "").replace("|", "\\|"),
                reasons=", ".join(item.get("reasons", [])),
                linked_products=linked_products.replace("|", "\\|"),
            )
        )

    return "\n".join(lines)



def write_report(report: dict[str, object], json_output: Path, md_output: Path) -> None:
    json_output.parent.mkdir(parents=True, exist_ok=True)
    md_output.parent.mkdir(parents=True, exist_ok=True)
    json_output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_output.write_text(render_markdown(report), encoding="utf-8")



def main() -> None:
    parser = argparse.ArgumentParser(description="Audit media_assets for Cloudinary folder conventions.")
    parser.add_argument("--expected-root", default=DEFAULT_EXPECTED_ROOT)
    parser.add_argument("--products-folder", default=DEFAULT_PRODUCTS_FOLDER)
    parser.add_argument("--json-output", default=str(DEFAULT_JSON_OUTPUT))
    parser.add_argument("--md-output", default=str(DEFAULT_MD_OUTPUT))
    args = parser.parse_args()

    with SessionLocal() as session:
        report = audit_media_assets(
            db=session,
            expected_root=args.expected_root,
            products_folder=args.products_folder,
        )

    json_output = Path(args.json_output)
    md_output = Path(args.md_output)
    write_report(report, json_output=json_output, md_output=md_output)

    summary = report["summary"]
    print(f"[OK] JSON report: {json_output}")
    print(f"[OK] Markdown report: {md_output}")
    print(
        "[SUMMARY] total={total} cloudinary={cloudinary} mismatched={mismatched}".format(
            total=summary.get("total_media_assets", 0),
            cloudinary=summary.get("cloudinary_assets", 0),
            mismatched=summary.get("mismatched_assets", 0),
        )
    )


if __name__ == "__main__":
    main()
