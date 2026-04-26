from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
import sys
from typing import Any
from urllib.parse import urlparse

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
  sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import admin as _admin_models  # noqa: F401
from app.models import content as _content_models  # noqa: F401
from app.models import media as _media_models  # noqa: F401
from app.models import navigation as _navigation_models  # noqa: F401
from app.models import news as _news_models  # noqa: F401
from app.models import organization as _organization_models  # noqa: F401
from app.models import projects as _project_models  # noqa: F401
from app.models import taxonomy as _taxonomy_models  # noqa: F401
from app.models.media import MediaAsset
from app.models.products import Product, ProductImage

DEFAULT_PRODUCT_ID_START = 662
DEFAULT_PRODUCT_ID_END = 680
DEFAULT_JSON_OUTPUT = PROJECT_ROOT / 'scripts' / 'reports' / 'repair_product_images_from_media_assets.json'
DEFAULT_MD_OUTPUT = PROJECT_ROOT / 'scripts' / 'reports' / 'repair_product_images_from_media_assets.md'


@dataclass
class RepairResult:
  product_id: int
  sku: str
  slug: str
  name: str
  status: str
  reason: str
  current_image_url_before: str
  image_url_after: str
  gallery_count_before: int
  gallery_count_after: int
  matched_media_count: int
  matched_media_ids: list[int]
  matched_storage_paths: list[str]


def parse_args() -> argparse.Namespace:
  parser = argparse.ArgumentParser(
    description='Repair tự động ảnh sản phẩm từ media_assets theo folder slug Cloudinary.',
  )
  parser.add_argument('--product-id-start', type=int, default=DEFAULT_PRODUCT_ID_START)
  parser.add_argument('--product-id-end', type=int, default=DEFAULT_PRODUCT_ID_END)
  parser.add_argument('--execute', action='store_true', help='Thực thi cập nhật DB. Mặc định chỉ dry-run.')
  parser.add_argument(
    '--force',
    action='store_true',
    help='Cho phép ghi đè cả những sản phẩm đã có image_url/gallery. Mặc định chỉ repair sản phẩm đang thiếu ảnh.',
  )
  parser.add_argument('--json-output', default=str(DEFAULT_JSON_OUTPUT))
  parser.add_argument('--md-output', default=str(DEFAULT_MD_OUTPUT))
  return parser.parse_args()


def normalize_text(value: Any) -> str:
  return str(value or '').strip()


def is_http_url(value: str | None) -> bool:
  raw = normalize_text(value)
  if not raw:
    return False
  parsed = urlparse(raw)
  return parsed.scheme in {'http', 'https'} and bool(parsed.netloc)


def dedupe_urls(urls: list[str]) -> list[str]:
  deduplicated: list[str] = []
  seen: set[str] = set()
  for url in urls:
    normalized = normalize_text(url)
    if not normalized or normalized in seen:
      continue
    seen.add(normalized)
    deduplicated.append(normalized)
  return deduplicated


def build_storage_pattern(slug: str) -> str:
  return f'china_web/products/{slug}/'


def load_candidate_products(session, product_id_start: int, product_id_end: int) -> list[Product]:
  return list(
    session.scalars(
      select(Product)
      .where(Product.id >= product_id_start, Product.id <= product_id_end)
      .order_by(Product.id)
    ).all()
  )


def load_matching_media(session, slug: str) -> list[MediaAsset]:
  pattern = build_storage_pattern(slug)
  rows = session.scalars(
    select(MediaAsset)
    .where(MediaAsset.asset_type == 'image')
    .where(MediaAsset.status == 'active')
    .where(MediaAsset.storage_path.is_not(None))
    .where(MediaAsset.url.is_not(None))
    .order_by(MediaAsset.id)
  ).all()

  matches: list[MediaAsset] = []
  for media in rows:
    storage_path = normalize_text(media.storage_path).lower()
    if pattern in storage_path and is_http_url(media.url):
      matches.append(media)
  return matches


def build_plan(*, product_id_start: int, product_id_end: int, force: bool) -> list[dict[str, Any]]:
  session = SessionLocal()
  try:
    products = load_candidate_products(session, product_id_start, product_id_end)
    plans: list[dict[str, Any]] = []

    for product in products:
      current_primary = normalize_text(product.image_url)
      existing_gallery = [
        normalize_text(image.url)
        for image in sorted(product.images or [], key=lambda item: (item.sort_order, item.id or 0))
        if normalize_text(image.url)
      ]
      matched_media = load_matching_media(session, normalize_text(product.slug))
      matched_urls = dedupe_urls([normalize_text(media.url) for media in matched_media])
      matched_media_ids = [int(media.id) for media in matched_media]
      matched_storage_paths = [normalize_text(media.storage_path) for media in matched_media]

      result = RepairResult(
        product_id=int(product.id),
        sku=normalize_text(product.sku),
        slug=normalize_text(product.slug),
        name=normalize_text(product.name),
        status='skipped',
        reason='',
        current_image_url_before=current_primary,
        image_url_after=current_primary,
        gallery_count_before=len(existing_gallery),
        gallery_count_after=len(existing_gallery),
        matched_media_count=len(matched_urls),
        matched_media_ids=matched_media_ids,
        matched_storage_paths=matched_storage_paths,
      )

      if not matched_urls:
        result.reason = 'Không tìm thấy media_assets nào khớp folder slug sản phẩm.'
        plans.append(asdict(result))
        continue

      if not force and (current_primary or existing_gallery):
        result.reason = 'Sản phẩm đã có ảnh, bỏ qua để tránh ghi đè. Dùng --force nếu muốn repair lại.'
        plans.append(asdict(result))
        continue

      final_primary = matched_urls[0]
      final_gallery = dedupe_urls(matched_urls[1:])

      result.image_url_after = final_primary
      result.gallery_count_after = len(final_gallery)

      if current_primary == final_primary and dedupe_urls(existing_gallery) == final_gallery:
        result.reason = 'Dữ liệu hiện tại đã khớp, không cần cập nhật.'
        plans.append(asdict(result))
        continue

      result.status = 'ready'
      result.reason = 'Sẵn sàng repair từ media_assets theo slug folder.'
      payload = asdict(result)
      payload['final_primary'] = final_primary
      payload['final_gallery'] = final_gallery
      plans.append(payload)

    return plans
  finally:
    session.close()


def execute_plan(plans: list[dict[str, Any]]) -> list[dict[str, Any]]:
  session = SessionLocal()
  try:
    results: list[dict[str, Any]] = []
    for plan in plans:
      if plan.get('status') != 'ready':
        results.append(plan)
        continue

      product = session.get(Product, int(plan['product_id']))
      if not product:
        results.append(
          {
            **plan,
            'status': 'skipped',
            'reason': 'Không tìm thấy sản phẩm lúc execute.',
          }
        )
        continue

      product.image_url = normalize_text(plan.get('final_primary'))
      product.images.clear()
      for index, url in enumerate(plan.get('final_gallery', [])):
        product.images.append(ProductImage(url=normalize_text(url), alt=product.name, sort_order=index))

      session.add(product)
      results.append(
        {
          **plan,
          'status': 'updated',
          'reason': 'Đã repair ảnh từ media_assets vào products/product_images.',
        }
      )

    session.commit()
    return results
  except Exception:
    session.rollback()
    raise
  finally:
    session.close()


def build_report(*, product_id_start: int, product_id_end: int, execute: bool, force: bool) -> dict[str, Any]:
  plans = build_plan(product_id_start=product_id_start, product_id_end=product_id_end, force=force)
  results = execute_plan(plans) if execute else plans
  summary = {
    'product_id_start': product_id_start,
    'product_id_end': product_id_end,
    'execute': execute,
    'force': force,
    'products_total': len(results),
    'ready_total': len([item for item in results if item['status'] == 'ready']),
    'updated_total': len([item for item in results if item['status'] == 'updated']),
    'skipped_total': len([item for item in results if item['status'] == 'skipped']),
    'matched_media_total': sum(int(item.get('matched_media_count', 0)) for item in results),
  }
  return {
    'summary': summary,
    'results': results,
  }


def render_markdown(report: dict[str, Any]) -> str:
  summary = report.get('summary', {})
  rows = report.get('results', [])
  lines = [
    '# Repair ảnh sản phẩm từ media_assets',
    '',
    '## Tóm tắt',
    '',
    f"- Product range: **{summary.get('product_id_start', 0)} → {summary.get('product_id_end', 0)}**",
    f"- Execute mode: **{summary.get('execute', False)}**",
    f"- Force mode: **{summary.get('force', False)}**",
    f"- Tổng sản phẩm xét: **{summary.get('products_total', 0)}**",
    f"- Ready: **{summary.get('ready_total', 0)}**",
    f"- Updated: **{summary.get('updated_total', 0)}**",
    f"- Skipped: **{summary.get('skipped_total', 0)}**",
    f"- Tổng media match: **{summary.get('matched_media_total', 0)}**",
    '',
  ]

  if not rows:
    lines.append('Không có sản phẩm nào để repair.')
    return '\n'.join(lines)

  columns = [
    'product_id',
    'sku',
    'slug',
    'name',
    'status',
    'matched_media_count',
    'current_image_url_before',
    'image_url_after',
    'gallery_count_before',
    'gallery_count_after',
    'matched_media_ids',
    'reason',
  ]
  lines.append('| ' + ' | '.join(columns) + ' |')
  lines.append('| ' + ' | '.join(['---'] * len(columns)) + ' |')
  for row in rows:
    values: list[str] = []
    for column in columns:
      value = row.get(column, '')
      if isinstance(value, list):
        value = ', '.join(str(item) for item in value)
      values.append(str(value).replace('|', '\\|').replace('\n', '<br>'))
    lines.append('| ' + ' | '.join(values) + ' |')
  return '\n'.join(lines)


def write_outputs(report: dict[str, Any], *, json_output: Path, md_output: Path) -> None:
  json_output.parent.mkdir(parents=True, exist_ok=True)
  md_output.parent.mkdir(parents=True, exist_ok=True)
  json_output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
  md_output.write_text(render_markdown(report), encoding='utf-8')


def main() -> None:
  args = parse_args()
  report = build_report(
    product_id_start=args.product_id_start,
    product_id_end=args.product_id_end,
    execute=args.execute,
    force=args.force,
  )
  json_output = Path(args.json_output)
  md_output = Path(args.md_output)
  write_outputs(report, json_output=json_output, md_output=md_output)

  print(f'[OK] JSON report: {json_output}')
  print(f'[OK] Markdown report: {md_output}')
  print(
    '[SUMMARY] mode={mode} products={products} ready={ready} updated={updated} skipped={skipped} matched_media={matched_media}'.format(
      mode='execute' if args.execute else 'dry-run',
      products=report['summary'].get('products_total', 0),
      ready=report['summary'].get('ready_total', 0),
      updated=report['summary'].get('updated_total', 0),
      skipped=report['summary'].get('skipped_total', 0),
      matched_media=report['summary'].get('matched_media_total', 0),
    )
  )


if __name__ == '__main__':
  main()
