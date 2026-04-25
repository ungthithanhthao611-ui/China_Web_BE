from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any
import unicodedata

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db.session import SessionLocal
from scripts.audit_media_assets_cloudinary import audit_media_assets, normalize_path


DEFAULT_EXPECTED_ROOT = "China_web"
DEFAULT_PRODUCTS_FOLDER = "products"
DEFAULT_JSON_OUTPUT = PROJECT_ROOT / "scripts" / "reports" / "media_assets_migration_plan.json"
DEFAULT_MD_OUTPUT = PROJECT_ROOT / "scripts" / "reports" / "media_assets_migration_plan.md"


def slugify(value: str | None) -> str:
    raw = str(value or "").strip().lower()
    raw = raw.replace("đ", "d")
    raw = unicodedata.normalize("NFD", raw)
    raw = "".join(char for char in raw if unicodedata.category(char) != "Mn")
    raw = re.sub(r"[^a-z0-9]+", "-", raw)
    return raw.strip("-")


def choose_linked_product(item: dict[str, Any]) -> dict[str, Any] | None:
    linked_products = item.get("linked_products") or []
    if not linked_products:
        return None

    with_slug = [product for product in linked_products if str(product.get("slug") or "").strip()]
    if with_slug:
        return with_slug[0]
    return linked_products[0]


def current_public_id(item: dict[str, Any]) -> str:
    storage_path = normalize_path(item.get("storage_path"))
    if storage_path:
        return storage_path

    url = str(item.get("url") or "")
    match = re.search(r"/upload/(?:v\d+/)?(.+?)(?:\.[a-z0-9]+)?(?:\?|$)", url, flags=re.IGNORECASE)
    return normalize_path(match.group(1) if match else "")


def build_target_plan(item: dict[str, Any], expected_root: str, products_folder: str) -> dict[str, Any]:
    linked_product = choose_linked_product(item)
    reasons = item.get("reasons") or []
    file_name = str(item.get("file_name") or "").strip()
    title = str(item.get("title") or "").strip()
    current_id = current_public_id(item)
    current_file_slug = slugify(Path(file_name).stem if file_name else title)

    if linked_product and str(linked_product.get("slug") or "").strip():
        product_slug = slugify(linked_product.get("slug"))
        target_folder = normalize_path(f"{expected_root}/{products_folder}/{product_slug}")
        target_asset_name = current_file_slug or product_slug or f"media-{item.get('media_id')}"
        target_public_id = normalize_path(f"{target_folder}/{target_asset_name}")
        target_url_hint = f"https://res.cloudinary.com/<cloud_name>/image/upload/<version>/{target_public_id}"
        return {
            "migration_status": "ready",
            "review_notes": [],
            "target_folder": target_folder,
            "target_public_id": target_public_id,
            "target_url_hint": target_url_hint,
            "linked_product": linked_product,
            "why": reasons,
        }

    review_notes: list[str] = []
    if linked_product and not str(linked_product.get("slug") or "").strip():
        review_notes.append("Sản phẩm liên kết chưa có slug nên chưa thể tính folder đích chắc chắn.")
    if not linked_product:
        review_notes.append("Asset chưa liên kết sản phẩm hoặc thuộc module khác; cần quyết định chuẩn folder riêng.")
    if "wrong_root_folder" in reasons and str(item.get("storage_path") or "").startswith("seed/"):
        review_notes.append("Asset seed cũ đang ở folder seed/. Nên xác nhận module sử dụng trước khi migrate.")

    return {
        "migration_status": "manual_review",
        "review_notes": review_notes,
        "target_folder": None,
        "target_public_id": None,
        "target_url_hint": None,
        "linked_product": linked_product,
        "why": reasons,
    }


def build_plan(expected_root: str, products_folder: str) -> dict[str, Any]:
    with SessionLocal() as session:
        audit_report = audit_media_assets(
            db=session,
            expected_root=expected_root,
            products_folder=products_folder,
        )

    plan_items: list[dict[str, Any]] = []
    ready_count = 0
    review_count = 0

    for item in audit_report.get("mismatches", []):
        target = build_target_plan(item, expected_root=expected_root, products_folder=products_folder)
        if target["migration_status"] == "ready":
            ready_count += 1
        else:
            review_count += 1

        plan_items.append(
            {
                "media_id": item.get("media_id"),
                "title": item.get("title"),
                "file_name": item.get("file_name"),
                "current_url": item.get("url"),
                "current_storage_path": item.get("storage_path"),
                "current_public_id": current_public_id(item),
                "reasons": item.get("reasons", []),
                **target,
            }
        )

    return {
        "summary": {
            "expected_root": normalize_path(expected_root),
            "expected_products_folder": normalize_path(products_folder),
            "total_mismatched_assets": len(plan_items),
            "ready_to_migrate": ready_count,
            "manual_review_required": review_count,
        },
        "plan": plan_items,
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    plan = report["plan"]
    lines = [
        "# Kế hoạch migrate Cloudinary media_assets",
        "",
        "## Tóm tắt",
        "",
        f"- Root đích: `{summary.get('expected_root', '')}`",
        f"- Folder sản phẩm đích: `{summary.get('expected_products_folder', '')}`",
        f"- Tổng asset sai chuẩn: **{summary.get('total_mismatched_assets', 0)}**",
        f"- Có thể migrate tự động: **{summary.get('ready_to_migrate', 0)}**",
        f"- Cần review thủ công: **{summary.get('manual_review_required', 0)}**",
        "",
        "## Chi tiết kế hoạch",
        "",
    ]

    if not plan:
        lines.append("Không có asset sai chuẩn để lập kế hoạch migrate.")
        return "\n".join(lines)

    lines.extend(
        [
            "| media_id | current_storage_path | target_public_id | status | linked_product | reasons | notes |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )

    for item in plan:
        linked_product = item.get("linked_product") or {}
        linked_product_label = "-"
        if linked_product:
            linked_product_label = (
                f"#{linked_product.get('product_id')} / "
                f"{linked_product.get('slug') or '-'} / "
                f"{linked_product.get('source') or '-'}"
            )
        lines.append(
            "| {media_id} | {current_storage_path} | {target_public_id} | {status} | {linked_product} | {reasons} | {notes} |".format(
                media_id=item.get("media_id", ""),
                current_storage_path=str(item.get("current_storage_path") or "").replace("|", "\\|"),
                target_public_id=str(item.get("target_public_id") or "").replace("|", "\\|"),
                status=item.get("migration_status", ""),
                linked_product=linked_product_label.replace("|", "\\|"),
                reasons=", ".join(item.get("reasons") or []).replace("|", "\\|"),
                notes="; ".join(item.get("review_notes") or []).replace("|", "\\|"),
            )
        )

    return "\n".join(lines)


def write_report(report: dict[str, Any], json_output: Path, md_output: Path) -> None:
    json_output.parent.mkdir(parents=True, exist_ok=True)
    md_output.parent.mkdir(parents=True, exist_ok=True)
    json_output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_output.write_text(render_markdown(report), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build migration plan for Cloudinary media assets with mismatched folders.")
    parser.add_argument("--expected-root", default=DEFAULT_EXPECTED_ROOT)
    parser.add_argument("--products-folder", default=DEFAULT_PRODUCTS_FOLDER)
    parser.add_argument("--json-output", default=str(DEFAULT_JSON_OUTPUT))
    parser.add_argument("--md-output", default=str(DEFAULT_MD_OUTPUT))
    args = parser.parse_args()

    report = build_plan(expected_root=args.expected_root, products_folder=args.products_folder)
    json_output = Path(args.json_output)
    md_output = Path(args.md_output)
    write_report(report, json_output=json_output, md_output=md_output)

    summary = report["summary"]
    print(f"[OK] JSON plan: {json_output}")
    print(f"[OK] Markdown plan: {md_output}")
    print(
        "[SUMMARY] total={total} ready={ready} manual_review={review}".format(
            total=summary.get("total_mismatched_assets", 0),
            ready=summary.get("ready_to_migrate", 0),
            review=summary.get("manual_review_required", 0),
        )
    )


if __name__ == "__main__":
    main()
