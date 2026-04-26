from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any
from urllib.parse import urlparse

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
  sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import text

from app.db.session import SessionLocal, engine

DEFAULT_JSON_OUTPUT = PROJECT_ROOT / 'scripts' / 'reports' / 'assign_primary_from_gallery.json'
DEFAULT_MD_OUTPUT = PROJECT_ROOT / 'scripts' / 'reports' / 'assign_primary_from_gallery.md'


def parse_args() -> argparse.Namespace:
  parser = argparse.ArgumentParser(
    description='Tự động gán products.image_url từ ảnh gallery đầu tiên cho các sản phẩm đang thiếu ảnh chính.',
  )
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


def load_candidates() -> list[dict[str, Any]]:
  with engine.connect() as conn:
    rows = conn.execute(
      text(
        '''
        WITH first_gallery AS (
          SELECT
            pi.product_id,
            pi.id AS product_image_id,
            COALESCE(pi.url, '') AS gallery_url,
            ROW_NUMBER() OVER (
              PARTITION BY pi.product_id
              ORDER BY pi.sort_order, pi.id
            ) AS rn
          FROM product_images pi
        )
        SELECT
          p.id AS product_id,
          p.slug,
          p.name,
          p.sku,
          COALESCE(p.image_url, '') AS current_image_url,
          fg.product_image_id,
          COALESCE(fg.gallery_url, '') AS suggested_image_url
        FROM products p
        LEFT JOIN first_gallery fg ON fg.product_id = p.id AND fg.rn = 1
        WHERE COALESCE(p.image_url, '') = ''
        ORDER BY p.id
        '''
      )
    ).mappings().all()

  candidates: list[dict[str, Any]] = []
  for row in rows:
    suggested_image_url = normalize_text(row.get('suggested_image_url'))
    candidates.append(
      {
        'product_id': int(row['product_id']),
        'slug': normalize_text(row.get('slug')),
        'name': normalize_text(row.get('name')),
        'sku': normalize_text(row.get('sku')),
        'current_image_url': normalize_text(row.get('current_image_url')),
        'product_image_id': row.get('product_image_id'),
        'suggested_image_url': suggested_image_url,
        'can_assign': bool(row.get('product_image_id')) and is_http_url(suggested_image_url),
      }
    )
  return candidates


def execute_updates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
  session = SessionLocal()
  results: list[dict[str, Any]] = []
  try:
    for candidate in candidates:
      result = {
        **candidate,
        'status': 'skipped',
        'reason': '',
      }

      if candidate['current_image_url']:
        result['reason'] = 'Sản phẩm đã có image_url, không cập nhật.'
        results.append(result)
        continue

      if not candidate['product_image_id']:
        result['reason'] = 'Không có ảnh gallery đầu tiên để gán.'
        results.append(result)
        continue

      if not candidate['can_assign']:
        result['reason'] = 'URL gallery đầu tiên không hợp lệ.'
        results.append(result)
        continue

      session.execute(
        text(
          '''
          UPDATE products
          SET image_url = :image_url
          WHERE id = :product_id AND COALESCE(image_url, '') = ''
          '''
        ),
        {
          'product_id': candidate['product_id'],
          'image_url': candidate['suggested_image_url'],
        },
      )
      result['status'] = 'updated'
      result['reason'] = 'Đã gán image_url từ gallery đầu tiên.'
      results.append(result)

    session.commit()
    return results
  except Exception:
    session.rollback()
    raise
  finally:
    session.close()


def build_report(*, execute: bool) -> dict[str, Any]:
  candidates = load_candidates()
  if execute:
    results = execute_updates(candidates)
  else:
    results = []
    for candidate in candidates:
      status = 'ready' if candidate['can_assign'] else 'skipped'
      reason = 'Sẵn sàng gán image_url từ gallery đầu tiên.' if candidate['can_assign'] else (
        'Không có ảnh gallery đầu tiên để gán.' if not candidate['product_image_id'] else 'URL gallery đầu tiên không hợp lệ.'
      )
      results.append(
        {
          **candidate,
          'status': status,
          'reason': reason,
        }
      )

  summary = {
    'execute': execute,
    'total_candidates': len(results),
    'ready_or_updated_total': len([row for row in results if row['status'] in {'ready', 'updated'}]),
    'updated_total': len([row for row in results if row['status'] == 'updated']),
    'skipped_total': len([row for row in results if row['status'] == 'skipped']),
  }
  return {
    'summary': summary,
    'results': results,
  }


def render_markdown(report: dict[str, Any]) -> str:
  summary = report['summary']
  lines = [
    '# Gán ảnh chính từ gallery đầu tiên',
    '',
    '## Tóm tắt',
    '',
    f"- Execute mode: **{summary.get('execute', False)}**",
    f"- Tổng candidate: **{summary.get('total_candidates', 0)}**",
    f"- Ready/Updated: **{summary.get('ready_or_updated_total', 0)}**",
    f"- Updated: **{summary.get('updated_total', 0)}**",
    f"- Skipped: **{summary.get('skipped_total', 0)}**",
    '',
  ]

  rows = report['results']
  if not rows:
    lines.append('Không có sản phẩm nào cần xét gán ảnh chính.')
    return '\n'.join(lines)

  columns = [
    'product_id',
    'sku',
    'slug',
    'name',
    'product_image_id',
    'suggested_image_url',
    'status',
    'reason',
  ]
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
    '[SUMMARY] mode={mode} total={total} ready_or_updated={ready_or_updated} updated={updated} skipped={skipped}'.format(
      mode='execute' if args.execute else 'dry-run',
      total=report['summary'].get('total_candidates', 0),
      ready_or_updated=report['summary'].get('ready_or_updated_total', 0),
      updated=report['summary'].get('updated_total', 0),
      skipped=report['summary'].get('skipped_total', 0),
    )
  )


if __name__ == '__main__':
  main()
