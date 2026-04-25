from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
import sys
from typing import Any

import cloudinary.uploader
from sqlalchemy import select

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db.session import SessionLocal
from app.models.media import MediaAsset
from app.models.products import Product, ProductImage
from app.models.projects import ProjectProduct  # noqa: F401
from app.services.media import _configure_cloudinary
from scripts.build_media_assets_migration_plan import build_plan


DEFAULT_EXPECTED_ROOT = "China_web"
DEFAULT_PRODUCTS_FOLDER = "products"
DEFAULT_JSON_OUTPUT = PROJECT_ROOT / "scripts" / "reports" / "media_assets_migration_run.json"
DEFAULT_MD_OUTPUT = PROJECT_ROOT / "scripts" / "reports" / "media_assets_migration_run.md"


@dataclass
class MigrationResult:
    media_id: int
    title: str | None
    status: str
    dry_run: bool
    current_public_id: str | None
    target_public_id: str | None
    current_url: str | None
    target_url: str | None
    affected_products: list[int]
    affected_product_images: list[int]
    notes: list[str]
    error: str | None = None



def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Safely migrate ready Cloudinary product assets. Default mode is dry-run.",
    )
    parser.add_argument("--expected-root", default=DEFAULT_EXPECTED_ROOT)
    parser.add_argument("--products-folder", default=DEFAULT_PRODUCTS_FOLDER)
    parser.add_argument("--execute", action="store_true", help="Thực thi rename trên Cloudinary và cập nhật DB.")
    parser.add_argument("--limit", type=int, default=0, help="Giới hạn số asset ready sẽ xử lý. 0 = không giới hạn.")
    parser.add_argument("--json-output", default=str(DEFAULT_JSON_OUTPUT))
    parser.add_argument("--md-output", default=str(DEFAULT_MD_OUTPUT))
    return parser.parse_args()



def build_target_url(current_url: str, target_public_id: str) -> str:
    current = str(current_url or "").strip()
    if not current:
        return current

    marker = "/upload/"
    if marker not in current:
        return current

    prefix, suffix = current.split(marker, 1)
    version_prefix = ""
    tail = suffix
    if tail.startswith("v") and "/" in tail:
        maybe_version, remainder = tail.split("/", 1)
        if maybe_version[1:].isdigit():
            version_prefix = f"{maybe_version}/"
            tail = remainder

    extension = ""
    if "." in tail:
        extension = "." + tail.rsplit(".", 1)[1].split("?", 1)[0]

    query = ""
    if "?" in current:
        query = "?" + current.split("?", 1)[1]

    return f"{prefix}{marker}{version_prefix}{target_public_id}{extension}{query}"



def load_ready_items(expected_root: str, products_folder: str, limit: int) -> list[dict[str, Any]]:
    plan = build_plan(expected_root=expected_root, products_folder=products_folder)
    ready_items = [item for item in plan.get("plan", []) if item.get("migration_status") == "ready"]
    if limit and limit > 0:
        return ready_items[:limit]
    return ready_items



def migrate_one(item: dict[str, Any], *, execute: bool) -> MigrationResult:
    media_id = int(item["media_id"])
    current_public_id = str(item.get("current_public_id") or "").strip()
    target_public_id = str(item.get("target_public_id") or "").strip()
    current_url = str(item.get("current_url") or "").strip()
    target_url = build_target_url(current_url, target_public_id)
    notes: list[str] = []

    with SessionLocal() as session:
        media = session.get(MediaAsset, media_id)
        if not media:
            return MigrationResult(
                media_id=media_id,
                title=item.get("title"),
                status="failed",
                dry_run=not execute,
                current_public_id=current_public_id,
                target_public_id=target_public_id,
                current_url=current_url,
                target_url=target_url,
                affected_products=[],
                affected_product_images=[],
                notes=notes,
                error="Không tìm thấy media_assets record tương ứng.",
            )

        matched_products = session.scalars(
            select(Product).where(Product.image_url == current_url)
        ).all()
        matched_gallery = session.scalars(
            select(ProductImage).where(ProductImage.url == current_url)
        ).all()

        product_ids = [product.id for product in matched_products]
        product_image_ids = [image.id for image in matched_gallery]

        notes.append(f"products.image_url cần cập nhật: {len(product_ids)}")
        notes.append(f"product_images.url cần cập nhật: {len(product_image_ids)}")

        if not execute:
            notes.append("Dry-run: chưa rename Cloudinary và chưa cập nhật DB.")
            return MigrationResult(
                media_id=media_id,
                title=media.title,
                status="dry_run_ready",
                dry_run=True,
                current_public_id=current_public_id,
                target_public_id=target_public_id,
                current_url=current_url,
                target_url=target_url,
                affected_products=product_ids,
                affected_product_images=product_image_ids,
                notes=notes,
            )

        if not current_public_id or not target_public_id:
            return MigrationResult(
                media_id=media_id,
                title=media.title,
                status="failed",
                dry_run=False,
                current_public_id=current_public_id,
                target_public_id=target_public_id,
                current_url=current_url,
                target_url=target_url,
                affected_products=product_ids,
                affected_product_images=product_image_ids,
                notes=notes,
                error="Thiếu current_public_id hoặc target_public_id.",
            )

        rename_result = cloudinary.uploader.rename(
            current_public_id,
            target_public_id,
            overwrite=False,
            invalidate=True,
            resource_type="image",
        )
        secure_url = str(rename_result.get("secure_url") or rename_result.get("url") or "").strip()
        if secure_url:
            target_url = secure_url
        else:
            notes.append("Cloudinary không trả secure_url mới, dùng URL suy luận từ current_url.")

        media.storage_path = target_public_id
        media.url = target_url
        session.add(media)

        for product in matched_products:
            product.image_url = target_url
            session.add(product)

        for image in matched_gallery:
            image.url = target_url
            session.add(image)

        session.commit()
        notes.append("Đã rename trên Cloudinary và cập nhật DB thành công.")
        return MigrationResult(
            media_id=media_id,
            title=media.title,
            status="migrated",
            dry_run=False,
            current_public_id=current_public_id,
            target_public_id=target_public_id,
            current_url=current_url,
            target_url=target_url,
            affected_products=product_ids,
            affected_product_images=product_image_ids,
            notes=notes,
        )



def run_migration(*, expected_root: str, products_folder: str, execute: bool, limit: int) -> dict[str, Any]:
    ready_items = load_ready_items(expected_root=expected_root, products_folder=products_folder, limit=limit)

    if execute and ready_items:
        _configure_cloudinary()

    results: list[MigrationResult] = []
    for item in ready_items:
        try:
            results.append(migrate_one(item, execute=execute))
        except Exception as exc:  # noqa: BLE001
            results.append(
                MigrationResult(
                    media_id=int(item["media_id"]),
                    title=item.get("title"),
                    status="failed",
                    dry_run=not execute,
                    current_public_id=item.get("current_public_id"),
                    target_public_id=item.get("target_public_id"),
                    current_url=item.get("current_url"),
                    target_url=build_target_url(
                        str(item.get("current_url") or ""),
                        str(item.get("target_public_id") or ""),
                    ),
                    affected_products=[],
                    affected_product_images=[],
                    notes=["Xử lý bị dừng ở asset này; các asset khác vẫn tiếp tục."],
                    error=str(exc),
                )
            )

    summary = {
        "mode": "execute" if execute else "dry_run",
        "expected_root": expected_root,
        "expected_products_folder": products_folder,
        "selected_ready_items": len(ready_items),
        "success_count": sum(1 for item in results if item.status in {"dry_run_ready", "migrated"}),
        "failed_count": sum(1 for item in results if item.status == "failed"),
    }
    return {
        "summary": summary,
        "results": [asdict(item) for item in results],
    }



def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    results = report["results"]
    lines = [
        "# Kết quả migrate Cloudinary media_assets",
        "",
        "## Tóm tắt",
        "",
        f"- Chế độ: **{summary.get('mode', '')}**",
        f"- Root đích: `{summary.get('expected_root', '')}`",
        f"- Folder sản phẩm đích: `{summary.get('expected_products_folder', '')}`",
        f"- Ready items được chọn: **{summary.get('selected_ready_items', 0)}**",
        f"- Thành công / hợp lệ: **{summary.get('success_count', 0)}**",
        f"- Thất bại: **{summary.get('failed_count', 0)}**",
        "",
        "## Chi tiết",
        "",
        "| media_id | status | current_public_id | target_public_id | affected_products | affected_product_images | notes | error |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]

    for item in results:
        lines.append(
            "| {media_id} | {status} | {current_public_id} | {target_public_id} | {affected_products} | {affected_product_images} | {notes} | {error} |".format(
                media_id=item.get("media_id", ""),
                status=item.get("status", ""),
                current_public_id=str(item.get("current_public_id") or "").replace("|", "\\|"),
                target_public_id=str(item.get("target_public_id") or "").replace("|", "\\|"),
                affected_products=", ".join(str(value) for value in item.get("affected_products", [])),
                affected_product_images=", ".join(str(value) for value in item.get("affected_product_images", [])),
                notes="; ".join(item.get("notes", [])).replace("|", "\\|"),
                error=str(item.get("error") or "").replace("|", "\\|"),
            )
        )

    return "\n".join(lines)



def write_report(report: dict[str, Any], json_output: Path, md_output: Path) -> None:
    json_output.parent.mkdir(parents=True, exist_ok=True)
    md_output.parent.mkdir(parents=True, exist_ok=True)
    json_output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_output.write_text(render_markdown(report), encoding="utf-8")



def main() -> None:
    args = parse_args()
    report = run_migration(
        expected_root=args.expected_root,
        products_folder=args.products_folder,
        execute=args.execute,
        limit=args.limit,
    )
    json_output = Path(args.json_output)
    md_output = Path(args.md_output)
    write_report(report, json_output=json_output, md_output=md_output)

    summary = report["summary"]
    print(f"[OK] JSON run report: {json_output}")
    print(f"[OK] Markdown run report: {md_output}")
    print(
        "[SUMMARY] mode={mode} selected={selected} success={success} failed={failed}".format(
            mode=summary.get("mode", ""),
            selected=summary.get("selected_ready_items", 0),
            success=summary.get("success_count", 0),
            failed=summary.get("failed_count", 0),
        )
    )


if __name__ == "__main__":
    main()
