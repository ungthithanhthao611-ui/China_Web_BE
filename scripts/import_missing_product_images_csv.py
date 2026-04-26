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

from app.db.session import SessionLocal
from app.models import admin as _admin_models  # noqa: F401
from app.models import content as _content_models  # noqa: F401
from app.models import media as _media_models  # noqa: F401
from app.models import navigation as _navigation_models  # noqa: F401
from app.models import news as _news_models  # noqa: F401
from app.models import organization as _organization_models  # noqa: F401
from app.models import projects as _project_models  # noqa: F401
from app.models import taxonomy as _taxonomy_models  # noqa: F401
from app.models.products import Product, ProductImage

DEFAULT_CSV_INPUT = PROJECT_ROOT / 'scripts' / 'reports' / 'missing_product_images_template.csv'
DEFAULT_JSON_OUTPUT = PROJECT_ROOT / 'scripts' / 'reports' / 'import_missing_product_images.json'
DEFAULT_MD_OUTPUT = PROJECT_ROOT / 'scripts' / 'reports' / 'import_missing_product_images.md'


def parse_args() -> argparse.Namespace:
  parser = argparse.ArgumentParser(
    description='Import nhanh ảnh sản phẩm từ file CSV để cập nhật products.image_url và product_images.',
  )
  parser.add_argument('--csv-input', default=str(DEFAULT_CSV_INPUT))
  parser.add_argument('--execute', action='store_true', help='Thực thi cập nhật DB. Mặc định chỉ dry-run.')
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


def parse_multiline_urls(value: str | None) -> list[str]:
  raw = normalize_text(value)
  if not raw:
    return []

  urls: list[str] = []
  seen: set[str] = set()
  normalized_raw = raw.replace('\r', '\n')
  for line in normalized_raw.split('\n'):
    url = normalize_text(line)
    if not url or url in seen:
      continue
    seen.add(url)
    urls.append(url)
  return urls


def dedupe_gallery_urls(primary_url: str, gallery_urls: list[str]) -> list[str]:
  deduplicated: list[str] = []
  seen: set[str] = set()
  for url in gallery_urls:
    if not url or url == primary_url or url in seen:
      continue
    seen.add(url)
    deduplicated.append(url)
  return deduplicated


def load_csv_rows(csv_input: Path) -> list[dict[str, Any]]:
  with csv_input.open('r', encoding='utf-8-sig', newline='') as handle:
    reader = csv.DictReader(handle)
    rows: list[dict[str, Any]] = []
    for raw_row in reader:
      if not raw_row:
        continue
      product_id = normalize_text(raw_row.get('product_id'))
      if not product_id:
        continue
      rows.append({key: normalize_text(value) for key, value in raw_row.items()})
    return rows


def build_import_plan(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
  session = SessionLocal()
  plans: list[dict[str, Any]] = []
  try:
    for row in rows:
      product_id_raw = row.get('product_id')
      result = {
        'product_id': product_id_raw,
        'sku': row.get('sku', ''),
        'slug': row.get('slug', ''),
        'name': row.get('name', ''),
        'status': 'skipped',
        'reason': '',
        'current_image_url_before': '',
        'image_url_after': '',
        'gallery_count_before': 0,
        'gallery_count_after': 0,
        'import_gallery_count': 0,
      }

      try:
        product_id = int(product_id_raw or 0)
      except ValueError:
        result['reason'] = 'product_id không hợp lệ.'
        plans.append(result)
        continue

      product = session.get(Product, product_id)
      if not product:
        result['reason'] = 'Không tìm thấy sản phẩm trong DB.'
        plans.append(result)
        continue

      current_primary = normalize_text(product.image_url)
      existing_gallery = [item.url for item in sorted(product.images or [], key=lambda image: (image.sort_order, image.id or 0)) if normalize_text(item.url)]
      csv_primary = normalize_text(row.get('suggested_primary_image_url'))
      csv_gallery = parse_multiline_urls(row.get('new_gallery_urls_multiline'))

      result['current_image_url_before'] = current_primary
      result['gallery_count_before'] = len(existing_gallery)
      result['import_gallery_count'] = len(csv_gallery)

      if csv_primary and not is_http_url(csv_primary):
        result['reason'] = 'suggested_primary_image_url không phải URL hợp lệ.'
        plans.append(result)
        continue

      invalid_gallery_urls = [url for url in csv_gallery if not is_http_url(url)]
      if invalid_gallery_urls:
        result['reason'] = f'Có URL gallery không hợp lệ: {invalid_gallery_urls[0]}'
        plans.append(result)
        continue

      final_primary = csv_primary or current_primary
      if not final_primary and not csv_gallery:
        result['reason'] = 'Dòng CSV chưa có dữ liệu ảnh để import.'
        plans.append(result)
        continue

      if not final_primary and csv_gallery:
        result['reason'] = 'Có gallery mới nhưng chưa có ảnh chính. Hãy điền suggested_primary_image_url trước.'
        plans.append(result)
        continue

      final_gallery = existing_gallery
      if csv_gallery:
        final_gallery = dedupe_gallery_urls(final_primary, csv_gallery)
      else:
        final_gallery = dedupe_gallery_urls(final_primary, existing_gallery)

      result['image_url_after'] = final_primary
      result['gallery_count_after'] = len(final_gallery)

      if final_primary == current_primary and final_gallery == dedupe_gallery_urls(current_primary, existing_gallery):
        result['reason'] = 'Không có thay đổi mới để import.'
        plans.append(result)
        continue

      result['status'] = 'ready'
      result['reason'] = 'Sẵn sàng cập nhật sản phẩm từ CSV.'
      result['product_id'] = product_id
      result['final_primary'] = final_primary
      result['final_gallery'] = final_gallery
      plans.append(result)

    return plans
  finally:
    session.close()


def execute_import(plans: list[dict[str, Any]]) -> list[dict[str, Any]]:
  session = SessionLocal()
  results: list[dict[str, Any]] = []
  try:
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

      product.image_url = plan['final_primary']
      product.images.clear()
      for index, url in enumerate(plan['final_gallery']):
        product.images.append(ProductImage(url=url, alt=product.name, sort_order=index))

      session.add(product)
      results.append(
        {
          **plan,
          'status': 'updated',
          'reason': 'Đã import ảnh từ CSV vào DB.',
        }
      )

    session.commit()
    return results
  except Exception:
    session.rollback()
    raise
  finally:
    session.close()


def build_report(*, csv_input: Path, execute: bool) -> dict[str, Any]:
  rows = load_csv_rows(csv_input)
  plans = build_import_plan(rows)
  results = execute_import(plans) if execute else plans
  summary = {
    'csv_input': str(csv_input),
    'execute': execute,
    'rows_total': len(rows),
    'ready_total': len([item for item in results if item['status'] == 'ready']),
    'updated_total': len([item for item in results if item['status'] == 'updated']),
    'skipped_total': len([item for item in results if item['status'] == 'skipped']),
  }
  return {
    'summary': summary,
    'results': results,
  }


def render_markdown(report: dict[str, Any]) -> str:
  summary = report['summary']
  lines = [
    '# Import ảnh sản phẩm từ CSV',
    '',
    '## Tóm tắt',
    '',
    f"- CSV input: `{summary.get('csv_input', '')}`",
    f"- Execute mode: **{summary.get('execute', False)}**",
    f"- Tổng dòng CSV: **{summary.get('rows_total', 0)}**",
    f"- Ready: **{summary.get('ready_total', 0)}**",
    f"- Updated: **{summary.get('updated_total', 0)}**",
    f"- Skipped: **{summary.get('skipped_total', 0)}**",
    '',
    '## Quy ước import',
    '',
    '- Điền `suggested_primary_image_url` nếu muốn set/đổi ảnh chính.',
    '- Điền `new_gallery_urls_multiline` với mỗi URL trên một dòng nếu muốn ghi đè gallery.',
    '- Script tự loại bỏ URL gallery trùng với ảnh chính.',
    '- Nếu không điền gallery mới, script sẽ giữ gallery cũ nhưng vẫn loại ảnh trùng ảnh chính.',
    '',
  ]

  rows = report['results']
  if not rows:
    lines.append('Không có dữ liệu để import.')
    return '\n'.join(lines)

  columns = [
    'product_id',
    'sku',
    'slug',
    'name',
    'status',
    'current_image_url_before',
    'image_url_after',
    'gallery_count_before',
    'gallery_count_after',
    'import_gallery_count',
    'reason',
  ]
  lines.append('| ' + ' | '.join(columns) + ' |')
  lines.append('| ' + ' | '.join(['---'] * len(columns)) + ' |')
  for row in rows:
    values = [str(row.get(column, '')).replace('|', '\\|').replace('\n', '<br>') for column in columns]
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
  report = build_report(csv_input=csv_input, execute=args.execute)
  json_output = Path(args.json_output)
  md_output = Path(args.md_output)
  write_outputs(report, json_output=json_output, md_output=md_output)

  print(f'[OK] JSON report: {json_output}')
  print(f'[OK] Markdown report: {md_output}')
  print(
    '[SUMMARY] mode={mode} rows={rows} ready={ready} updated={updated} skipped={skipped}'.format(
      mode='execute' if args.execute else 'dry-run',
      rows=report['summary'].get('rows_total', 0),
      ready=report['summary'].get('ready_total', 0),
      updated=report['summary'].get('updated_total', 0),
      skipped=report['summary'].get('skipped_total', 0),
    )
  )


if __name__ == '__main__':
  main()
