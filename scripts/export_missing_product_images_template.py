from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
  sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import text

from app.db.session import engine

DEFAULT_JSON_OUTPUT = PROJECT_ROOT / 'scripts' / 'reports' / 'missing_product_images_template.json'
DEFAULT_MD_OUTPUT = PROJECT_ROOT / 'scripts' / 'reports' / 'missing_product_images_template.md'
DEFAULT_CSV_OUTPUT = PROJECT_ROOT / 'scripts' / 'reports' / 'missing_product_images_template.csv'


def parse_args() -> argparse.Namespace:
  parser = argparse.ArgumentParser(
    description='Xuất danh sách sản phẩm thiếu ảnh theo format nhập liệu để admin bổ sung nhanh.',
  )
  parser.add_argument('--json-output', default=str(DEFAULT_JSON_OUTPUT))
  parser.add_argument('--md-output', default=str(DEFAULT_MD_OUTPUT))
  parser.add_argument('--csv-output', default=str(DEFAULT_CSV_OUTPUT))
  return parser.parse_args()


def normalize_text(value: Any) -> str:
  return str(value or '').strip()


def load_state() -> dict[str, Any]:
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
        SELECT product_id, COALESCE(url, '') AS url, sort_order, id
        FROM product_images
        ORDER BY product_id, sort_order, id
        '''
      )
    ).mappings().all()

  gallery_by_product: dict[int, list[str]] = defaultdict(list)
  for row in gallery_rows:
    url = normalize_text(row.get('url'))
    if not url:
      continue
    gallery_by_product[int(row['product_id'])].append(url)

  products = []
  for row in product_rows:
    product_id = int(row['id'])
    image_url = normalize_text(row.get('image_url'))
    gallery_urls = gallery_by_product.get(product_id, [])
    products.append(
      {
        'product_id': product_id,
        'slug': normalize_text(row.get('slug')),
        'name': normalize_text(row.get('name')),
        'sku': normalize_text(row.get('sku')),
        'current_image_url': image_url,
        'gallery_count': len(gallery_urls),
        'first_gallery_url': gallery_urls[0] if gallery_urls else '',
        'gallery_urls': gallery_urls,
      }
    )

  return {
    'products': products,
  }


def build_report() -> dict[str, Any]:
  state = load_state()
  rows: list[dict[str, Any]] = []
  missing_primary_total = 0
  missing_any_image_total = 0

  for product in state['products']:
    has_primary = bool(product['current_image_url'])
    has_gallery = bool(product['gallery_urls'])

    if has_primary and has_gallery:
      status = 'ok'
      action = ''
    elif has_primary and not has_gallery:
      status = 'missing_gallery'
      action = 'Có thể bổ sung thêm ảnh liên quan nếu cần.'
    elif not has_primary and has_gallery:
      status = 'missing_primary'
      action = 'Có thể auto gán ảnh chính từ first_gallery_url hoặc chọn URL khác phù hợp hơn.'
      missing_primary_total += 1
    else:
      status = 'missing_all'
      action = 'Cần bổ sung cả ảnh chính và gallery.'
      missing_primary_total += 1
      missing_any_image_total += 1

    example_primary_image_url = (
      'https://res.cloudinary.com/<cloud-name>/image/upload/v1234567890/China_web/products/<slug>/primary.jpg'
    )
    example_gallery_urls_multiline = '\n'.join(
      [
        'https://res.cloudinary.com/<cloud-name>/image/upload/v1234567890/China_web/products/<slug>/gallery-01.jpg',
        'https://res.cloudinary.com/<cloud-name>/image/upload/v1234567890/China_web/products/<slug>/gallery-02.jpg',
      ]
    )
    csv_fill_instruction = (
      'Điền suggested_primary_image_url bằng 1 URL ảnh chính. '
      'Điền new_gallery_urls_multiline mỗi dòng 1 URL nếu muốn ghi đè gallery.'
    )

    rows.append(
      {
        'product_id': product['product_id'],
        'sku': product['sku'],
        'slug': product['slug'],
        'name': product['name'],
        'status': status,
        'current_image_url': product['current_image_url'],
        'first_gallery_url': product['first_gallery_url'],
        'gallery_count': product['gallery_count'],
        'suggested_primary_image_url': product['first_gallery_url'] if status == 'missing_primary' else '',
        'new_gallery_urls_multiline': '',
        'example_primary_image_url': example_primary_image_url,
        'example_gallery_urls_multiline': example_gallery_urls_multiline,
        'csv_fill_instruction': csv_fill_instruction,
        'admin_action_note': action,
      }
    )

  actionable_rows = [row for row in rows if row['status'] in {'missing_primary', 'missing_all', 'missing_gallery'}]

  return {
    'summary': {
      'products_total': len(rows),
      'actionable_rows_total': len(actionable_rows),
      'missing_primary_total': missing_primary_total,
      'missing_any_image_total': missing_any_image_total,
      'missing_gallery_only_total': len([row for row in rows if row['status'] == 'missing_gallery']),
    },
    'rows': rows,
    'actionable_rows': actionable_rows,
  }


def render_markdown(report: dict[str, Any]) -> str:
  summary = report['summary']
  rows = report['actionable_rows']
  lines = [
    '# Danh sách sản phẩm thiếu ảnh để admin bổ sung nhanh',
    '',
    '## Tóm tắt',
    '',
    f"- Tổng sản phẩm: **{summary.get('products_total', 0)}**",
    f"- Tổng dòng cần xử lý: **{summary.get('actionable_rows_total', 0)}**",
    f"- Thiếu ảnh chính: **{summary.get('missing_primary_total', 0)}**",
    f"- Thiếu toàn bộ ảnh: **{summary.get('missing_any_image_total', 0)}**",
    f"- Chỉ thiếu gallery: **{summary.get('missing_gallery_only_total', 0)}**",
    '',
    '## Hướng dẫn nhập nhanh',
    '',
    '- `suggested_primary_image_url`: điền đúng 1 URL ảnh chính.',
    '- `new_gallery_urls_multiline`: dán nhiều URL, mỗi dòng một ảnh.',
    '- `example_primary_image_url`: ví dụ format ảnh chính để admin nhìn theo.',
    '- `example_gallery_urls_multiline`: ví dụ nhiều URL gallery, mỗi URL một dòng.',
    '- `csv_fill_instruction`: ghi chú nhanh nhắc cách điền file CSV.',
    '- `admin_action_note`: gợi ý thao tác nhanh cho admin.',
    '',
  ]

  if not rows:
    lines.append('Không có sản phẩm nào cần bổ sung ảnh.')
    return '\n'.join(lines)

  columns = [
    'product_id',
    'sku',
    'slug',
    'name',
    'status',
    'current_image_url',
    'first_gallery_url',
    'suggested_primary_image_url',
    'new_gallery_urls_multiline',
    'example_primary_image_url',
    'example_gallery_urls_multiline',
    'csv_fill_instruction',
    'admin_action_note',
  ]
  lines.append('| ' + ' | '.join(columns) + ' |')
  lines.append('| ' + ' | '.join(['---'] * len(columns)) + ' |')
  for row in rows:
    values = [str(row.get(column, '')).replace('|', '\\|').replace('\n', '<br>') for column in columns]
    lines.append('| ' + ' | '.join(values) + ' |')

  return '\n'.join(lines)


def write_outputs(report: dict[str, Any], *, json_output: Path, md_output: Path, csv_output: Path) -> None:
  json_output.parent.mkdir(parents=True, exist_ok=True)
  md_output.parent.mkdir(parents=True, exist_ok=True)
  csv_output.parent.mkdir(parents=True, exist_ok=True)

  json_output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
  md_output.write_text(render_markdown(report), encoding='utf-8')

  fieldnames = [
    'product_id',
    'sku',
    'slug',
    'name',
    'status',
    'current_image_url',
    'first_gallery_url',
    'gallery_count',
    'suggested_primary_image_url',
    'new_gallery_urls_multiline',
    'example_primary_image_url',
    'example_gallery_urls_multiline',
    'csv_fill_instruction',
    'admin_action_note',
  ]
  with csv_output.open('w', encoding='utf-8-sig', newline='') as handle:
    writer = csv.DictWriter(handle, fieldnames=fieldnames)
    writer.writeheader()
    for row in report['actionable_rows']:
      writer.writerow({key: row.get(key, '') for key in fieldnames})


def main() -> None:
  args = parse_args()
  report = build_report()
  json_output = Path(args.json_output)
  md_output = Path(args.md_output)
  csv_output = Path(args.csv_output)
  write_outputs(report, json_output=json_output, md_output=md_output, csv_output=csv_output)

  print(f'[OK] JSON report: {json_output}')
  print(f'[OK] Markdown report: {md_output}')
  print(f'[OK] CSV template: {csv_output}')
  print(
    '[SUMMARY] actionable={actionable} missing_primary={missing_primary} missing_any_image={missing_any_image} missing_gallery_only={missing_gallery_only}'.format(
      actionable=report['summary'].get('actionable_rows_total', 0),
      missing_primary=report['summary'].get('missing_primary_total', 0),
      missing_any_image=report['summary'].get('missing_any_image_total', 0),
      missing_gallery_only=report['summary'].get('missing_gallery_only_total', 0),
    )
  )


if __name__ == '__main__':
  main()
