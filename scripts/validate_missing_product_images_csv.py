from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys
from typing import Any
from urllib.parse import urlparse

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
  sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import text

from app.db.session import engine
from app.models import admin as _admin_models  # noqa: F401
from app.models import content as _content_models  # noqa: F401
from app.models import media as _media_models  # noqa: F401
from app.models import navigation as _navigation_models  # noqa: F401
from app.models import news as _news_models  # noqa: F401
from app.models import organization as _organization_models  # noqa: F401
from app.models import projects as _project_models  # noqa: F401
from app.models import taxonomy as _taxonomy_models  # noqa: F401
from app.models import products as _product_models  # noqa: F401

DEFAULT_CSV_INPUT = PROJECT_ROOT / 'scripts' / 'reports' / 'missing_product_images_template.csv'
DEFAULT_JSON_OUTPUT = PROJECT_ROOT / 'scripts' / 'reports' / 'validate_missing_product_images.json'
DEFAULT_MD_OUTPUT = PROJECT_ROOT / 'scripts' / 'reports' / 'validate_missing_product_images.md'

REQUIRED_COLUMNS = [
  'product_id',
  'sku',
  'slug',
  'name',
  'suggested_primary_image_url',
  'new_gallery_urls_multiline',
]

PLACEHOLDER_TOKENS = ['<cloud-name>', '<slug>']


def parse_args() -> argparse.Namespace:
  parser = argparse.ArgumentParser(
    description='Validate-only file CSV ảnh sản phẩm trước khi import thật.',
  )
  parser.add_argument('--csv-input', default=str(DEFAULT_CSV_INPUT))
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


def contains_placeholder(value: str | None) -> bool:
  raw = normalize_text(value)
  return any(token in raw for token in PLACEHOLDER_TOKENS)


def parse_multiline_urls(value: str | None) -> list[str]:
  raw = normalize_text(value)
  if not raw:
    return []

  urls: list[str] = []
  normalized = raw.replace('\r', '\n')
  for line in normalized.split('\n'):
    url = normalize_text(line)
    if url:
      urls.append(url)
  return urls


def load_db_products() -> dict[int, dict[str, Any]]:
  with engine.connect() as conn:
    product_rows = conn.execute(
      text(
        '''
        SELECT id, COALESCE(sku, '') AS sku, COALESCE(slug, '') AS slug, COALESCE(name, '') AS name,
               COALESCE(image_url, '') AS image_url
        FROM products
        ORDER BY id
        '''
      )
    ).mappings().all()

    gallery_rows = conn.execute(
      text(
        '''
        SELECT product_id, COALESCE(url, '') AS url
        FROM product_images
        ORDER BY product_id, sort_order, id
        '''
      )
    ).mappings().all()

  gallery_count_by_product: dict[int, int] = {}
  for row in gallery_rows:
    product_id = int(row['product_id'])
    url = normalize_text(row.get('url'))
    if not url:
      continue
    gallery_count_by_product[product_id] = gallery_count_by_product.get(product_id, 0) + 1

  db_products: dict[int, dict[str, Any]] = {}
  for row in product_rows:
    product_id = int(row['id'])
    db_products[product_id] = {
      'product_id': product_id,
      'sku': normalize_text(row.get('sku')),
      'slug': normalize_text(row.get('slug')),
      'name': normalize_text(row.get('name')),
      'current_image_url': normalize_text(row.get('image_url')),
      'gallery_count': gallery_count_by_product.get(product_id, 0),
    }
  return db_products


def load_csv_with_meta(csv_input: Path) -> tuple[list[dict[str, Any]], list[str]]:
  with csv_input.open('r', encoding='utf-8-sig', newline='') as handle:
    reader = csv.DictReader(handle)
    fieldnames = list(reader.fieldnames or [])
    rows: list[dict[str, Any]] = []
    for index, raw_row in enumerate(reader, start=2):
      if not raw_row:
        continue
      normalized_row = {key: normalize_text(value) for key, value in raw_row.items()}
      if not any(normalized_row.values()):
        continue
      normalized_row['_csv_line_number'] = index
      rows.append(normalized_row)
    return rows, fieldnames


def build_row_result(row: dict[str, Any], db_products: dict[int, dict[str, Any]], seen_product_ids: set[int]) -> dict[str, Any]:
  csv_line_number = int(row.get('_csv_line_number', 0) or 0)
  product_id_raw = normalize_text(row.get('product_id'))
  csv_primary = normalize_text(row.get('suggested_primary_image_url'))
  csv_gallery_lines = parse_multiline_urls(row.get('new_gallery_urls_multiline'))

  errors: list[str] = []
  warnings: list[str] = []

  result = {
    'csv_line_number': csv_line_number,
    'product_id': product_id_raw,
    'sku': row.get('sku', ''),
    'slug': row.get('slug', ''),
    'name': row.get('name', ''),
    'status': 'PASS',
    'error_count': 0,
    'warning_count': 0,
    'errors': errors,
    'warnings': warnings,
    'current_image_url_db': '',
    'gallery_count_db': 0,
    'suggested_primary_image_url': csv_primary,
    'import_gallery_count': len(csv_gallery_lines),
  }

  try:
    product_id = int(product_id_raw)
  except ValueError:
    errors.append('product_id không phải số nguyên hợp lệ.')
    result['status'] = 'FAIL'
    result['error_count'] = len(errors)
    result['warning_count'] = len(warnings)
    return result

  result['product_id'] = product_id
  if product_id in seen_product_ids:
    errors.append('product_id bị trùng trong file CSV.')
  else:
    seen_product_ids.add(product_id)

  product = db_products.get(product_id)
  if not product:
    errors.append('Không tìm thấy sản phẩm trong DB.')
  else:
    result['current_image_url_db'] = product['current_image_url']
    result['gallery_count_db'] = product['gallery_count']

    if normalize_text(row.get('sku')) and normalize_text(row.get('sku')) != product['sku']:
      warnings.append(f"SKU trong CSV khác DB. CSV='{row.get('sku', '')}' | DB='{product['sku']}'")
    if normalize_text(row.get('slug')) and normalize_text(row.get('slug')) != product['slug']:
      warnings.append(f"Slug trong CSV khác DB. CSV='{row.get('slug', '')}' | DB='{product['slug']}'")
    if normalize_text(row.get('name')) and normalize_text(row.get('name')) != product['name']:
      warnings.append(f"Tên trong CSV khác DB. CSV='{row.get('name', '')}' | DB='{product['name']}'")

  if csv_primary:
    if contains_placeholder(csv_primary):
      errors.append('suggested_primary_image_url vẫn đang dùng placeholder mẫu, chưa thay URL thật.')
    elif not is_http_url(csv_primary):
      errors.append('suggested_primary_image_url không phải URL http/https hợp lệ.')

  if not csv_primary and csv_gallery_lines:
    errors.append('Có gallery mới nhưng chưa điền suggested_primary_image_url.')

  gallery_seen: set[str] = set()
  duplicate_gallery_urls: list[str] = []
  invalid_gallery_urls: list[str] = []
  placeholder_gallery_urls: list[str] = []
  gallery_same_as_primary: list[str] = []

  for url in csv_gallery_lines:
    if contains_placeholder(url):
      placeholder_gallery_urls.append(url)
      continue
    if not is_http_url(url):
      invalid_gallery_urls.append(url)
      continue
    if url in gallery_seen:
      duplicate_gallery_urls.append(url)
      continue
    gallery_seen.add(url)
    if csv_primary and url == csv_primary:
      gallery_same_as_primary.append(url)

  if placeholder_gallery_urls:
    errors.append('new_gallery_urls_multiline vẫn chứa URL ví dụ mẫu chưa thay bằng URL thật.')
  if invalid_gallery_urls:
    errors.append(f'Có URL gallery không hợp lệ: {invalid_gallery_urls[0]}')
  if duplicate_gallery_urls:
    warnings.append(f'Có URL gallery bị lặp trong cùng một ô CSV: {duplicate_gallery_urls[0]}')
  if gallery_same_as_primary:
    warnings.append('Gallery có URL trùng với ảnh chính; import sẽ tự loại bỏ URL trùng này.')

  if not csv_primary and not csv_gallery_lines:
    warnings.append('Dòng CSV này chưa được điền dữ liệu ảnh mới.')

  if product and not csv_primary and product['current_image_url']:
    warnings.append('Không điền suggested_primary_image_url; import sẽ giữ ảnh chính hiện tại trong DB.')

  if product and not csv_gallery_lines and product['gallery_count'] > 0:
    warnings.append('Không điền new_gallery_urls_multiline; import sẽ giữ gallery hiện tại trong DB.')

  result['error_count'] = len(errors)
  result['warning_count'] = len(warnings)
  if errors:
    result['status'] = 'FAIL'
  elif warnings:
    result['status'] = 'WARN'
  return result


def build_report(csv_input: Path) -> dict[str, Any]:
  rows, fieldnames = load_csv_with_meta(csv_input)
  missing_columns = [column for column in REQUIRED_COLUMNS if column not in fieldnames]
  db_products = load_db_products()

  header_status = 'PASS'
  header_issues: list[str] = []
  if missing_columns:
    header_status = 'FAIL'
    header_issues.append('Thiếu cột bắt buộc: ' + ', '.join(missing_columns))

  seen_product_ids: set[int] = set()
  results = [build_row_result(row, db_products, seen_product_ids) for row in rows]

  fail_total = len([item for item in results if item['status'] == 'FAIL'])
  warn_total = len([item for item in results if item['status'] == 'WARN'])
  pass_total = len([item for item in results if item['status'] == 'PASS'])

  overall_status = 'PASS'
  if header_status == 'FAIL' or fail_total > 0:
    overall_status = 'FAIL'
  elif warn_total > 0:
    overall_status = 'WARN'

  return {
    'summary': {
      'csv_input': str(csv_input),
      'overall_status': overall_status,
      'header_status': header_status,
      'rows_total': len(rows),
      'pass_total': pass_total,
      'warn_total': warn_total,
      'fail_total': fail_total,
      'missing_required_columns': missing_columns,
      'header_issues': header_issues,
    },
    'results': results,
  }


def render_issue_list(items: list[str]) -> str:
  if not items:
    return ''
  return '<br>'.join(f'- {item}' for item in items)


def render_markdown(report: dict[str, Any]) -> str:
  summary = report['summary']
  lines = [
    '# Validate file CSV ảnh sản phẩm trước khi import',
    '',
    '## Tóm tắt',
    '',
    f"- CSV input: `{summary.get('csv_input', '')}`",
    f"- Overall status: **{summary.get('overall_status', 'PASS')}**",
    f"- Header status: **{summary.get('header_status', 'PASS')}**",
    f"- Tổng dòng dữ liệu: **{summary.get('rows_total', 0)}**",
    f"- PASS: **{summary.get('pass_total', 0)}**",
    f"- WARN: **{summary.get('warn_total', 0)}**",
    f"- FAIL: **{summary.get('fail_total', 0)}**",
    '',
  ]

  header_issues = summary.get('header_issues', []) or []
  if header_issues:
    lines.extend([
      '## Lỗi header CSV',
      '',
      *[f'- {item}' for item in header_issues],
      '',
    ])

  lines.extend([
    '## Quy ước đánh giá',
    '',
    '- `PASS`: dòng hợp lệ, có thể import.',
    '- `WARN`: dòng chưa lỗi chặn nhưng có điểm cần kiểm tra lại.',
    '- `FAIL`: dòng có lỗi rõ ràng, chưa nên import.',
    '',
  ])

  rows = report['results']
  if not rows:
    lines.append('Không có dòng dữ liệu nào trong CSV.')
    return '\n'.join(lines)

  columns = [
    'csv_line_number',
    'product_id',
    'sku',
    'slug',
    'status',
    'error_count',
    'warning_count',
    'current_image_url_db',
    'gallery_count_db',
    'suggested_primary_image_url',
    'import_gallery_count',
    'errors',
    'warnings',
  ]
  lines.append('| ' + ' | '.join(columns) + ' |')
  lines.append('| ' + ' | '.join(['---'] * len(columns)) + ' |')
  for row in rows:
    values = []
    for column in columns:
      value = row.get(column, '')
      if column in {'errors', 'warnings'}:
        value = render_issue_list(value if isinstance(value, list) else [])
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
  csv_input = Path(args.csv_input)
  report = build_report(csv_input)
  json_output = Path(args.json_output)
  md_output = Path(args.md_output)
  write_outputs(report, json_output=json_output, md_output=md_output)

  print(f'[OK] JSON report: {json_output}')
  print(f'[OK] Markdown report: {md_output}')
  print(
    '[SUMMARY] status={status} rows={rows} pass={passed} warn={warn} fail={fail}'.format(
      status=report['summary'].get('overall_status', 'PASS'),
      rows=report['summary'].get('rows_total', 0),
      passed=report['summary'].get('pass_total', 0),
      warn=report['summary'].get('warn_total', 0),
      fail=report['summary'].get('fail_total', 0),
    )
  )


if __name__ == '__main__':
  main()
