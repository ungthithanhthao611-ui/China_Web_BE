from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from mimetypes import guess_type
from pathlib import Path
import sys
from typing import Any
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
  sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import or_, select

from app.db.session import SessionLocal
from app.models.admin import AdminUser  # noqa: F401
from app.models.media import MediaAsset
from scripts.audit_cloudinary_db_alignment import audit_alignment

DEFAULT_PREFIX = 'China_web'
DEFAULT_JSON_OUTPUT = PROJECT_ROOT / 'scripts' / 'reports' / 'cloudinary_media_assets_sync.json'
DEFAULT_MD_OUTPUT = PROJECT_ROOT / 'scripts' / 'reports' / 'cloudinary_media_assets_sync.md'


@dataclass
class SyncResult:
  public_id: str
  url: str
  status: str
  media_id: int | None
  title: str | None
  file_name: str | None
  asset_type: str
  mime_type: str | None
  size: int | None
  reason: str | None = None


def parse_args() -> argparse.Namespace:
  parser = argparse.ArgumentParser(
    description='Đồng bộ các Cloudinary asset còn thiếu vào bảng media_assets.',
  )
  parser.add_argument('--prefix', default=DEFAULT_PREFIX)
  parser.add_argument('--execute', action='store_true', help='Thực thi insert vào DB. Mặc định là dry-run.')
  parser.add_argument('--limit', type=int, default=0, help='Giới hạn số asset xử lý. 0 = không giới hạn.')
  parser.add_argument('--json-output', default=str(DEFAULT_JSON_OUTPUT))
  parser.add_argument('--md-output', default=str(DEFAULT_MD_OUTPUT))
  return parser.parse_args()


def normalize_text(value: Any) -> str:
  return str(value or '').strip()


def infer_asset_type(item: dict[str, Any]) -> str:
  asset_type = normalize_text(item.get('asset_type')).lower()
  resource_type = normalize_text(item.get('resource_type')).lower()

  if asset_type in {'image', 'video'}:
    return asset_type
  if resource_type == 'image':
    return 'image'
  if resource_type == 'video':
    return 'video'
  return 'file'


def infer_file_name(item: dict[str, Any]) -> str | None:
  display_name = normalize_text(item.get('display_name'))
  public_id = normalize_text(item.get('public_id'))
  file_format = normalize_text(item.get('format'))

  base_name = display_name or Path(public_id).name
  if not base_name:
    return None

  if file_format and not base_name.lower().endswith(f'.{file_format.lower()}'):
    return f'{base_name}.{file_format}'
  return base_name


def infer_mime_type(item: dict[str, Any], file_name: str | None, asset_type: str) -> str | None:
  guessed, _ = guess_type(file_name or normalize_text(item.get('secure_url')))
  if guessed:
    return guessed
  if asset_type == 'image':
    return 'image/*'
  if asset_type == 'video':
    return 'video/*'
  return None


def load_missing_assets(prefix: str, limit: int) -> list[dict[str, Any]]:
  report = audit_alignment(prefix=prefix)
  items = report.get('cloudinary_missing_in_media_assets', [])
  if limit > 0:
    return list(items[:limit])
  return list(items)


def sync_missing_assets(*, prefix: str, execute: bool, limit: int) -> dict[str, Any]:
  missing_assets = load_missing_assets(prefix=prefix, limit=limit)
  results: list[SyncResult] = []

  with SessionLocal() as session:
    for item in missing_assets:
      public_id = normalize_text(item.get('public_id'))
      url = normalize_text(item.get('secure_url') or item.get('url'))
      file_name = infer_file_name(item)
      asset_type = infer_asset_type(item)
      mime_type = infer_mime_type(item, file_name, asset_type)
      title = normalize_text(item.get('display_name')) or file_name or Path(public_id).name or None
      size = item.get('bytes')

      if not public_id or not url:
        results.append(
          SyncResult(
            public_id=public_id,
            url=url,
            status='failed',
            media_id=None,
            title=title,
            file_name=file_name,
            asset_type=asset_type,
            mime_type=mime_type,
            size=size,
            reason='Thiếu public_id hoặc URL Cloudinary hợp lệ.',
          )
        )
        continue

      existing = session.scalar(
        select(MediaAsset).where(
          or_(
            MediaAsset.storage_path == public_id,
            MediaAsset.url == url,
          )
        )
      )
      if existing:
        results.append(
          SyncResult(
            public_id=public_id,
            url=url,
            status='skipped_existing',
            media_id=existing.id,
            title=existing.title,
            file_name=existing.file_name,
            asset_type=existing.asset_type,
            mime_type=existing.mime_type,
            size=existing.size,
            reason='Đã tồn tại record media_assets theo storage_path/url.',
          )
        )
        continue

      if not execute:
        results.append(
          SyncResult(
            public_id=public_id,
            url=url,
            status='dry_run_ready',
            media_id=None,
            title=title,
            file_name=file_name,
            asset_type=asset_type,
            mime_type=mime_type,
            size=size,
            reason='Dry-run: chưa insert DB.',
          )
        )
        continue

      record = MediaAsset(
        uuid=str(uuid4()),
        file_name=file_name,
        url=url,
        storage_path=public_id,
        asset_type=asset_type,
        mime_type=mime_type,
        width=None,
        height=None,
        size=size if isinstance(size, int) else None,
        alt_text=None,
        title=title,
        uploaded_by=None,
        status='active',
      )
      session.add(record)
      session.flush()

      results.append(
        SyncResult(
          public_id=public_id,
          url=url,
          status='inserted',
          media_id=record.id,
          title=record.title,
          file_name=record.file_name,
          asset_type=record.asset_type,
          mime_type=record.mime_type,
          size=record.size,
          reason=None,
        )
      )

    if execute:
      session.commit()
    else:
      session.rollback()

  summary = {
    'prefix': prefix,
    'execute': execute,
    'total_candidates': len(missing_assets),
    'inserted': sum(1 for item in results if item.status == 'inserted'),
    'dry_run_ready': sum(1 for item in results if item.status == 'dry_run_ready'),
    'skipped_existing': sum(1 for item in results if item.status == 'skipped_existing'),
    'failed': sum(1 for item in results if item.status == 'failed'),
  }
  return {
    'summary': summary,
    'results': [asdict(item) for item in results],
  }


def render_markdown(report: dict[str, Any]) -> str:
  summary = report.get('summary', {})
  results = report.get('results', [])

  lines = [
    '# Kết quả đồng bộ Cloudinary → media_assets',
    '',
    '## Tóm tắt',
    '',
    f"- Prefix: `{summary.get('prefix', '')}`",
    f"- Chế độ: **{'execute' if summary.get('execute') else 'dry_run'}**",
    f"- Tổng asset cần xét: **{summary.get('total_candidates', 0)}**",
    f"- Insert thành công: **{summary.get('inserted', 0)}**",
    f"- Dry-run sẵn sàng insert: **{summary.get('dry_run_ready', 0)}**",
    f"- Skip vì đã tồn tại: **{summary.get('skipped_existing', 0)}**",
    f"- Failed: **{summary.get('failed', 0)}**",
    '',
    '## Chi tiết',
    '',
    '| public_id | status | media_id | asset_type | file_name | title | reason |',
    '| --- | --- | --- | --- | --- | --- | --- |',
  ]

  for item in results:
    lines.append(
      '| {public_id} | {status} | {media_id} | {asset_type} | {file_name} | {title} | {reason} |'.format(
        public_id=str(item.get('public_id') or '').replace('|', '\\|'),
        status=item.get('status', ''),
        media_id=item.get('media_id', ''),
        asset_type=item.get('asset_type', ''),
        file_name=str(item.get('file_name') or '').replace('|', '\\|'),
        title=str(item.get('title') or '').replace('|', '\\|'),
        reason=str(item.get('reason') or '').replace('|', '\\|'),
      )
    )

  return '\n'.join(lines)


def write_report(report: dict[str, Any], *, json_output: Path, md_output: Path) -> None:
  json_output.parent.mkdir(parents=True, exist_ok=True)
  md_output.parent.mkdir(parents=True, exist_ok=True)
  json_output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
  md_output.write_text(render_markdown(report), encoding='utf-8')


def main() -> None:
  args = parse_args()
  report = sync_missing_assets(prefix=args.prefix, execute=args.execute, limit=args.limit)
  json_output = Path(args.json_output)
  md_output = Path(args.md_output)
  write_report(report, json_output=json_output, md_output=md_output)

  summary = report.get('summary', {})
  print(f'[OK] JSON report: {json_output}')
  print(f'[OK] Markdown report: {md_output}')
  print(
    '[SUMMARY] mode={mode} total={total} inserted={inserted} ready={ready} skipped={skipped} failed={failed}'.format(
      mode='execute' if summary.get('execute') else 'dry_run',
      total=summary.get('total_candidates', 0),
      inserted=summary.get('inserted', 0),
      ready=summary.get('dry_run_ready', 0),
      skipped=summary.get('skipped_existing', 0),
      failed=summary.get('failed', 0),
    )
  )


if __name__ == '__main__':
  main()
