from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
import sys
from typing import Any
from urllib.parse import urlparse

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
  sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import text

from app.db.session import engine
from scripts.audit_cloudinary_db_alignment import audit_alignment, normalize_cloudinary_url, normalize_text

DEFAULT_PREFIX = 'China_web'
DEFAULT_JSON_OUTPUT = PROJECT_ROOT / 'scripts' / 'reports' / 'product_image_system_audit.json'
DEFAULT_MD_OUTPUT = PROJECT_ROOT / 'scripts' / 'reports' / 'product_image_system_audit.md'


def parse_args() -> argparse.Namespace:
  parser = argparse.ArgumentParser(
    description='Audit tổng thể kiến trúc ảnh sản phẩm: products.image_url, product_images, media_assets và Cloudinary.',
  )
  parser.add_argument('--prefix', default=DEFAULT_PREFIX)
  parser.add_argument('--json-output', default=str(DEFAULT_JSON_OUTPUT))
  parser.add_argument('--md-output', default=str(DEFAULT_MD_OUTPUT))
  return parser.parse_args()


def is_http_url(value: str | None) -> bool:
  raw = normalize_text(value)
  if not raw:
    return False
  parsed = urlparse(raw)
  return parsed.scheme in {'http', 'https'} and bool(parsed.netloc)


def load_product_image_state() -> dict[str, Any]:
  with engine.connect() as conn:
    product_rows = conn.execute(
      text(
        '''
        SELECT id, slug, name, sku, COALESCE(image_url, '') AS image_url
        FROM products
        ORDER BY id
        '''
      )
    ).mappings().all()

    gallery_rows = conn.execute(
      text(
        '''
        SELECT pi.id, pi.product_id, COALESCE(pi.url, '') AS url, COALESCE(pi.alt, '') AS alt, pi.sort_order
        FROM product_images pi
        ORDER BY pi.product_id, pi.sort_order, pi.id
        '''
      )
    ).mappings().all()

  products = [
    {
      'id': int(row['id']),
      'slug': row.get('slug'),
      'name': row.get('name'),
      'sku': row.get('sku'),
      'image_url': normalize_text(row.get('image_url')),
    }
    for row in product_rows
  ]

  gallery_by_product: dict[int, list[dict[str, Any]]] = defaultdict(list)
  for row in gallery_rows:
    product_id = int(row['product_id'])
    gallery_by_product[product_id].append(
      {
        'id': int(row['id']),
        'url': normalize_text(row.get('url')),
        'alt': normalize_text(row.get('alt')),
        'sort_order': int(row.get('sort_order') or 0),
      }
    )

  return {
    'products': products,
    'gallery_by_product': gallery_by_product,
  }


def build_lookup(rows: list[dict[str, Any]], key: str) -> dict[str, list[dict[str, Any]]]:
  lookup: dict[str, list[dict[str, Any]]] = defaultdict(list)
  for row in rows:
    value = normalize_text(row.get(key))
    if value:
      lookup[value].append(row)
  return lookup


def audit_product_consistency(alignment_report: dict[str, Any]) -> dict[str, Any]:
  state = load_product_image_state()
  products = state['products']
  gallery_by_product = state['gallery_by_product']

  db_refs_without_media_asset = build_lookup(alignment_report.get('db_refs_without_media_asset', []), 'url')
  db_refs_missing_on_cloudinary = build_lookup(alignment_report.get('db_refs_missing_on_cloudinary', []), 'url')

  products_missing_primary: list[dict[str, Any]] = []
  products_invalid_primary_url: list[dict[str, Any]] = []
  products_primary_missing_media_asset: list[dict[str, Any]] = []
  products_primary_missing_on_cloudinary: list[dict[str, Any]] = []
  products_gallery_contains_primary: list[dict[str, Any]] = []
  products_gallery_duplicate_urls: list[dict[str, Any]] = []
  products_invalid_gallery_urls: list[dict[str, Any]] = []
  products_gallery_missing_media_asset: list[dict[str, Any]] = []
  products_gallery_missing_on_cloudinary: list[dict[str, Any]] = []
  products_without_any_image: list[dict[str, Any]] = []

  for product in products:
    product_id = int(product['id'])
    primary_url = normalize_text(product.get('image_url'))
    gallery_items = gallery_by_product.get(product_id, [])
    gallery_urls = [normalize_text(item.get('url')) for item in gallery_items if normalize_text(item.get('url'))]

    base_payload = {
      'product_id': product_id,
      'slug': product.get('slug'),
      'name': product.get('name'),
      'sku': product.get('sku'),
    }

    if not primary_url and not gallery_urls:
      products_without_any_image.append(base_payload)

    if not primary_url:
      products_missing_primary.append(base_payload)
    elif not is_http_url(primary_url):
      products_invalid_primary_url.append({
        **base_payload,
        'image_url': primary_url,
      })

    if primary_url and db_refs_without_media_asset.get(primary_url):
      products_primary_missing_media_asset.append({
        **base_payload,
        'image_url': primary_url,
      })

    if primary_url and db_refs_missing_on_cloudinary.get(primary_url):
      products_primary_missing_on_cloudinary.append({
        **base_payload,
        'image_url': primary_url,
      })

    if primary_url and primary_url in gallery_urls:
      duplicate_ids = [item['id'] for item in gallery_items if normalize_text(item.get('url')) == primary_url]
      products_gallery_contains_primary.append({
        **base_payload,
        'image_url': primary_url,
        'gallery_image_ids': duplicate_ids,
      })

    gallery_counter = Counter(gallery_urls)
    duplicate_gallery_urls = [url for url, count in gallery_counter.items() if count > 1]
    if duplicate_gallery_urls:
      products_gallery_duplicate_urls.append({
        **base_payload,
        'duplicate_urls': duplicate_gallery_urls,
      })

    invalid_gallery_items = [
      {
        'product_image_id': item['id'],
        'url': item['url'],
      }
      for item in gallery_items
      if item.get('url') and not is_http_url(item.get('url'))
    ]
    if invalid_gallery_items:
      products_invalid_gallery_urls.append({
        **base_payload,
        'items': invalid_gallery_items,
      })

    missing_media_items = [
      {
        'product_image_id': item['id'],
        'url': item['url'],
      }
      for item in gallery_items
      if item.get('url') and db_refs_without_media_asset.get(normalize_text(item.get('url')))
    ]
    if missing_media_items:
      products_gallery_missing_media_asset.append({
        **base_payload,
        'items': missing_media_items,
      })

    missing_cloud_items = [
      {
        'product_image_id': item['id'],
        'url': item['url'],
      }
      for item in gallery_items
      if item.get('url') and db_refs_missing_on_cloudinary.get(normalize_text(item.get('url')))
    ]
    if missing_cloud_items:
      products_gallery_missing_on_cloudinary.append({
        **base_payload,
        'items': missing_cloud_items,
      })

  return {
    'products_missing_primary': products_missing_primary,
    'products_invalid_primary_url': products_invalid_primary_url,
    'products_primary_missing_media_asset': products_primary_missing_media_asset,
    'products_primary_missing_on_cloudinary': products_primary_missing_on_cloudinary,
    'products_gallery_contains_primary': products_gallery_contains_primary,
    'products_gallery_duplicate_urls': products_gallery_duplicate_urls,
    'products_invalid_gallery_urls': products_invalid_gallery_urls,
    'products_gallery_missing_media_asset': products_gallery_missing_media_asset,
    'products_gallery_missing_on_cloudinary': products_gallery_missing_on_cloudinary,
    'products_without_any_image': products_without_any_image,
  }


def determine_health_status(*, summary: dict[str, Any], product_checks: dict[str, Any]) -> tuple[str, list[str]]:
  fail_reasons: list[str] = []
  warn_reasons: list[str] = []

  hard_fail_map = {
    'cloudinary_missing_in_media_assets_total': 'Cloudinary còn asset chưa vào media_assets',
    'media_assets_missing_on_cloudinary_total': 'media_assets có record nhưng file đã mất trên Cloudinary',
    'db_refs_without_media_asset_total': 'products/product_images còn URL chưa map tới media_assets',
    'db_refs_missing_on_cloudinary_total': 'products/product_images còn URL chết trên Cloudinary',
    'duplicate_media_asset_public_ids_total': 'media_assets còn public_id trùng',
  }
  for key, label in hard_fail_map.items():
    if int(summary.get(key, 0) or 0) > 0:
      fail_reasons.append(f'{label}: {summary.get(key, 0)}')

  if product_checks['products_gallery_contains_primary']:
    fail_reasons.append(
      f"Có {len(product_checks['products_gallery_contains_primary'])} sản phẩm bị lặp ảnh chính trong gallery"
    )
  if product_checks['products_gallery_duplicate_urls']:
    fail_reasons.append(
      f"Có {len(product_checks['products_gallery_duplicate_urls'])} sản phẩm có URL gallery bị trùng"
    )
  if product_checks['products_invalid_primary_url']:
    fail_reasons.append(
      f"Có {len(product_checks['products_invalid_primary_url'])} sản phẩm có image_url không hợp lệ"
    )
  if product_checks['products_invalid_gallery_urls']:
    fail_reasons.append(
      f"Có {len(product_checks['products_invalid_gallery_urls'])} sản phẩm có URL gallery không hợp lệ"
    )

  if product_checks['products_missing_primary']:
    warn_reasons.append(
      f"Có {len(product_checks['products_missing_primary'])} sản phẩm chưa có ảnh chính"
    )
  if product_checks['products_without_any_image']:
    warn_reasons.append(
      f"Có {len(product_checks['products_without_any_image'])} sản phẩm chưa có bất kỳ ảnh nào"
    )

  if fail_reasons:
    return 'FAIL', fail_reasons + warn_reasons
  if warn_reasons:
    return 'WARN', warn_reasons
  return 'PASS', ['Không phát hiện bất thường trọng yếu trong hệ thống ảnh sản phẩm.']


def render_rows(title: str, rows: list[dict[str, Any]], columns: list[str]) -> list[str]:
  lines = ['', f'## {title}', '']
  if not rows:
    lines.append('Không có dữ liệu bất thường.')
    return lines

  lines.append('| ' + ' | '.join(columns) + ' |')
  lines.append('| ' + ' | '.join(['---'] * len(columns)) + ' |')
  for row in rows:
    values = [str(row.get(column, '')).replace('|', '\\|') for column in columns]
    lines.append('| ' + ' | '.join(values) + ' |')
  return lines


def render_markdown(report: dict[str, Any]) -> str:
  summary = report['summary']
  product_summary = report['product_summary']

  lines = [
    '# Audit tổng thể hệ thống ảnh sản phẩm',
    '',
    '## Trạng thái tổng quan',
    '',
    f"- Health status: **{report.get('health_status', 'UNKNOWN')}**",
    f"- Prefix Cloudinary audit: `{summary.get('cloudinary_prefix_checked', '')}`",
    f"- Tổng media_assets: **{summary.get('media_assets_total', 0)}**",
    f"- Tổng URL ảnh sản phẩm/galleries: **{summary.get('product_url_refs_total', 0)}**",
    f"- Cloudinary còn thiếu trong media_assets: **{summary.get('cloudinary_missing_in_media_assets_total', 0)}**",
    f"- media_assets mất file trên Cloudinary: **{summary.get('media_assets_missing_on_cloudinary_total', 0)}**",
    f"- DB refs chưa map media_assets: **{summary.get('db_refs_without_media_asset_total', 0)}**",
    f"- DB refs mất file trên Cloudinary: **{summary.get('db_refs_missing_on_cloudinary_total', 0)}**",
    f"- Duplicate public_id trong media_assets: **{summary.get('duplicate_media_asset_public_ids_total', 0)}**",
    f"- Sản phẩm thiếu ảnh chính: **{product_summary.get('products_missing_primary_total', 0)}**",
    f"- Sản phẩm thiếu hoàn toàn ảnh: **{product_summary.get('products_without_any_image_total', 0)}**",
    f"- Sản phẩm lặp ảnh chính trong gallery: **{product_summary.get('products_gallery_contains_primary_total', 0)}**",
    f"- Sản phẩm có gallery trùng URL: **{product_summary.get('products_gallery_duplicate_urls_total', 0)}**",
    '',
    '## Diễn giải',
    '',
  ]

  for item in report.get('health_reasons', []):
    lines.append(f'- {item}')

  lines.extend(
    render_rows(
      'Sản phẩm thiếu ảnh chính',
      report['product_checks']['products_missing_primary'],
      ['product_id', 'slug', 'name', 'sku'],
    )
  )
  lines.extend(
    render_rows(
      'Sản phẩm không có bất kỳ ảnh nào',
      report['product_checks']['products_without_any_image'],
      ['product_id', 'slug', 'name', 'sku'],
    )
  )
  lines.extend(
    render_rows(
      'Sản phẩm bị lặp ảnh chính trong gallery',
      report['product_checks']['products_gallery_contains_primary'],
      ['product_id', 'slug', 'name', 'image_url', 'gallery_image_ids'],
    )
  )
  lines.extend(
    render_rows(
      'Sản phẩm có gallery bị trùng URL',
      report['product_checks']['products_gallery_duplicate_urls'],
      ['product_id', 'slug', 'name', 'duplicate_urls'],
    )
  )
  lines.extend(
    render_rows(
      'Sản phẩm có ảnh chính không hợp lệ',
      report['product_checks']['products_invalid_primary_url'],
      ['product_id', 'slug', 'name', 'image_url'],
    )
  )
  lines.extend(
    render_rows(
      'Sản phẩm có gallery URL không hợp lệ',
      report['product_checks']['products_invalid_gallery_urls'],
      ['product_id', 'slug', 'name', 'items'],
    )
  )
  lines.extend(
    render_rows(
      'Sản phẩm có ảnh chính chưa map media_assets',
      report['product_checks']['products_primary_missing_media_asset'],
      ['product_id', 'slug', 'name', 'image_url'],
    )
  )
  lines.extend(
    render_rows(
      'Sản phẩm có ảnh chính chết trên Cloudinary',
      report['product_checks']['products_primary_missing_on_cloudinary'],
      ['product_id', 'slug', 'name', 'image_url'],
    )
  )
  lines.extend(
    render_rows(
      'Sản phẩm có gallery chưa map media_assets',
      report['product_checks']['products_gallery_missing_media_asset'],
      ['product_id', 'slug', 'name', 'items'],
    )
  )
  lines.extend(
    render_rows(
      'Sản phẩm có gallery chết trên Cloudinary',
      report['product_checks']['products_gallery_missing_on_cloudinary'],
      ['product_id', 'slug', 'name', 'items'],
    )
  )
  lines.extend(
    render_rows(
      'public_id trùng trong media_assets',
      report['alignment']['duplicate_media_asset_public_ids'],
      ['public_id', 'media_ids'],
    )
  )

  return '\n'.join(lines)


def build_report(prefix: str) -> dict[str, Any]:
  alignment = audit_alignment(prefix=prefix)
  summary = alignment.get('summary', {})
  product_checks = audit_product_consistency(alignment)

  product_summary = {
    'products_missing_primary_total': len(product_checks['products_missing_primary']),
    'products_invalid_primary_url_total': len(product_checks['products_invalid_primary_url']),
    'products_primary_missing_media_asset_total': len(product_checks['products_primary_missing_media_asset']),
    'products_primary_missing_on_cloudinary_total': len(product_checks['products_primary_missing_on_cloudinary']),
    'products_gallery_contains_primary_total': len(product_checks['products_gallery_contains_primary']),
    'products_gallery_duplicate_urls_total': len(product_checks['products_gallery_duplicate_urls']),
    'products_invalid_gallery_urls_total': len(product_checks['products_invalid_gallery_urls']),
    'products_gallery_missing_media_asset_total': len(product_checks['products_gallery_missing_media_asset']),
    'products_gallery_missing_on_cloudinary_total': len(product_checks['products_gallery_missing_on_cloudinary']),
    'products_without_any_image_total': len(product_checks['products_without_any_image']),
  }

  health_status, health_reasons = determine_health_status(summary=summary, product_checks=product_checks)
  return {
    'health_status': health_status,
    'health_reasons': health_reasons,
    'summary': summary,
    'product_summary': product_summary,
    'product_checks': product_checks,
    'alignment': alignment,
  }


def write_report(report: dict[str, Any], *, json_output: Path, md_output: Path) -> None:
  json_output.parent.mkdir(parents=True, exist_ok=True)
  md_output.parent.mkdir(parents=True, exist_ok=True)
  json_output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
  md_output.write_text(render_markdown(report), encoding='utf-8')


def main() -> None:
  args = parse_args()
  report = build_report(prefix=args.prefix)
  json_output = Path(args.json_output)
  md_output = Path(args.md_output)
  write_report(report, json_output=json_output, md_output=md_output)

  print(f'[OK] JSON report: {json_output}')
  print(f'[OK] Markdown report: {md_output}')
  print(
    '[SUMMARY] health={health} cloudinary_missing_in_media_assets={c_missing} media_missing_on_cloudinary={m_missing} db_refs_without_media={db_missing_media} db_refs_missing_on_cloudinary={db_missing_cloud} products_missing_primary={products_missing_primary} products_without_any_image={products_without_any}'.format(
      health=report.get('health_status', 'UNKNOWN'),
      c_missing=report['summary'].get('cloudinary_missing_in_media_assets_total', 0),
      m_missing=report['summary'].get('media_assets_missing_on_cloudinary_total', 0),
      db_missing_media=report['summary'].get('db_refs_without_media_asset_total', 0),
      db_missing_cloud=report['summary'].get('db_refs_missing_on_cloudinary_total', 0),
      products_missing_primary=report['product_summary'].get('products_missing_primary_total', 0),
      products_without_any=report['product_summary'].get('products_without_any_image_total', 0),
    )
  )


if __name__ == '__main__':
  main()
