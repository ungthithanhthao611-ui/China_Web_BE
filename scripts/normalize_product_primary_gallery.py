from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
  sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import text

from app.db.session import SessionLocal, engine

DEFAULT_JSON_OUTPUT = PROJECT_ROOT / 'scripts' / 'reports' / 'normalize_product_primary_gallery.json'
DEFAULT_MD_OUTPUT = PROJECT_ROOT / 'scripts' / 'reports' / 'normalize_product_primary_gallery.md'


def parse_args() -> argparse.Namespace:
  parser = argparse.ArgumentParser(
    description='Loại bỏ product_images bị trùng với products.image_url để giữ tách biệt ảnh chính và gallery.',
  )
  parser.add_argument('--execute', action='store_true', help='Thực thi xóa các dòng gallery trùng. Mặc định chỉ dry-run.')
  parser.add_argument('--json-output', default=str(DEFAULT_JSON_OUTPUT))
  parser.add_argument('--md-output', default=str(DEFAULT_MD_OUTPUT))
  return parser.parse_args()


def normalize_text(value: Any) -> str:
  return str(value or '').strip()


def load_duplicates() -> list[dict[str, Any]]:
  with engine.connect() as conn:
    rows = conn.execute(
      text(
        '''
        SELECT
          p.id AS product_id,
          p.slug,
          p.name,
          p.sku,
          COALESCE(p.image_url, '') AS image_url,
          pi.id AS product_image_id,
          COALESCE(pi.url, '') AS gallery_url,
          pi.sort_order
        FROM products p
        JOIN product_images pi ON pi.product_id = p.id
        WHERE COALESCE(p.image_url, '') <> ''
          AND COALESCE(pi.url, '') <> ''
          AND p.image_url = pi.url
        ORDER BY p.id, pi.sort_order, pi.id
        '''
      )
    ).mappings().all()

  return [
    {
      'product_id': int(row['product_id']),
      'slug': normalize_text(row.get('slug')),
      'name': normalize_text(row.get('name')),
      'sku': normalize_text(row.get('sku')),
      'image_url': normalize_text(row.get('image_url')),
      'product_image_id': int(row['product_image_id']),
      'gallery_url': normalize_text(row.get('gallery_url')),
      'sort_order': int(row.get('sort_order') or 0),
    }
    for row in rows
  ]


def execute_cleanup(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
  session = SessionLocal()
  results: list[dict[str, Any]] = []
  try:
    for row in rows:
      session.execute(
        text(
          '''
          DELETE FROM product_images
          WHERE id = :product_image_id
            AND product_id = :product_id
            AND COALESCE(url, '') = :gallery_url
          '''
        ),
        {
          'product_image_id': row['product_image_id'],
          'product_id': row['product_id'],
          'gallery_url': row['gallery_url'],
        },
      )
      results.append({
        **row,
        'status': 'deleted',
        'reason': 'Đã xóa gallery row bị trùng với image_url.',
      })
    session.commit()
    return results
  except Exception:
    session.rollback()
    raise
  finally:
    session.close()


def build_report(*, execute: bool) -> dict[str, Any]:
  rows = load_duplicates()
  results = execute_cleanup(rows) if execute else [
    {
      **row,
      'status': 'ready',
      'reason': 'Sẵn sàng xóa gallery row bị trùng với image_url.',
    }
    for row in rows
  ]
  return {
    'summary': {
      'execute': execute,
      'duplicates_total': len(results),
      'deleted_total': len([item for item in results if item['status'] == 'deleted']),
    },
    'results': results,
  }


def render_markdown(report: dict[str, Any]) -> str:
  summary = report['summary']
  lines = [
    '# Chuẩn hóa ảnh chính và gallery',
    '',
    '## Tóm tắt',
    '',
    f"- Execute mode: **{summary.get('execute', False)}**",
    f"- Duplicate rows: **{summary.get('duplicates_total', 0)}**",
    f"- Deleted rows: **{summary.get('deleted_total', 0)}**",
    '',
  ]

  rows = report['results']
  if not rows:
    lines.append('Không có dòng gallery nào bị trùng với image_url.')
    return '\n'.join(lines)

  columns = ['product_id', 'sku', 'slug', 'name', 'product_image_id', 'sort_order', 'status', 'reason']
  lines.append('| ' + ' | '.join(columns) + ' |')
  lines.append('| ' + ' | '.join(['---'] * len(columns)) + ' |')
  for row in rows:
    values = [str(row.get(column, '')).replace('|', '\\|') for column in columns]
    lines.append('| ' + ' | '.join(values) + ' |')
  return '\n'.join(lines)


def write_outputs(report: dict[str, Any], *, json_output: Path, md_output: Path) -> None:
  json_output.parent.mkdir(parents=True, exist_ok=True)
  md_output.parent.mkdir(parents=True, exist_ok=True)
  json_output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
  md_output.write_text(render_markdown(report), encoding='utf-8')


def main() -> None:
  args = parse_args()
  report = build_report(execute=args.execute)
  json_output = Path(args.json_output)
  md_output = Path(args.md_output)
  write_outputs(report, json_output=json_output, md_output=md_output)
  print(f'[OK] JSON report: {json_output}')
  print(f'[OK] Markdown report: {md_output}')
  print(
    '[SUMMARY] mode={mode} duplicates={duplicates} deleted={deleted}'.format(
      mode='execute' if args.execute else 'dry-run',
      duplicates=report['summary'].get('duplicates_total', 0),
      deleted=report['summary'].get('deleted_total', 0),
    )
  )


if __name__ == '__main__':
  main()
