from __future__ import annotations

import argparse
import json
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
import sys
from urllib.parse import urlparse

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
  sys.path.insert(0, str(PROJECT_ROOT))

import cloudinary
import cloudinary.api
from sqlalchemy import text

from app.core.config import settings
from app.db.session import engine

DEFAULT_JSON_OUTPUT = PROJECT_ROOT / 'scripts' / 'reports' / 'cloudinary_db_alignment.json'
DEFAULT_MD_OUTPUT = PROJECT_ROOT / 'scripts' / 'reports' / 'cloudinary_db_alignment.md'


@dataclass
class DbUrlReference:
  source: str
  record_id: int
  product_id: int | None
  product_slug: str | None
  product_name: str | None
  url: str
  public_id_guess: str | None


@dataclass
class CloudinaryResourceEntry:
  public_id: str
  resource_type: str
  asset_type: str | None
  secure_url: str
  url: str | None
  display_name: str | None
  format: str | None
  bytes: int | None


@dataclass
class MediaAssetRecord:
  media_id: int
  title: str | None
  file_name: str | None
  url: str
  storage_path: str | None


def normalize_text(value: str | None) -> str:
  return str(value or '').strip()


def normalize_cloudinary_url(value: str | None) -> str:
  raw = normalize_text(value)
  if not raw:
    return ''

  parsed = urlparse(raw)
  if not parsed.scheme or not parsed.netloc:
    return raw.rstrip('/')

  return parsed._replace(query='', fragment='').geturl().rstrip('/')


def extract_public_id_from_cloudinary_url(value: str | None) -> str | None:
  raw = normalize_text(value)
  if not raw or 'res.cloudinary.com/' not in raw:
    return None

  parsed = urlparse(raw)
  path = parsed.path.strip('/')
  segments = [segment for segment in path.split('/') if segment]
  if len(segments) < 4:
    return None

  try:
    upload_index = segments.index('upload')
  except ValueError:
    return None

  tail = segments[upload_index + 1 :]
  if not tail:
    return None

  if tail[0].startswith('v') and tail[0][1:].isdigit():
    tail = tail[1:]
  if not tail:
    return None

  public_path = '/'.join(tail)
  suffix = Path(public_path).suffix
  if suffix:
    public_path = public_path[: -len(suffix)]
  return public_path or None


def configure_cloudinary() -> None:
  if settings.cloudinary_url.strip():
    cloudinary.config(cloudinary_url=settings.cloudinary_url, secure=True)
    return

  cloudinary.config(
    cloud_name=settings.cloudinary_cloud_name,
    api_key=settings.cloudinary_api_key,
    api_secret=settings.cloudinary_api_secret,
    secure=True,
  )


def fetch_cloudinary_resources(prefix: str | None) -> list[CloudinaryResourceEntry]:
  configure_cloudinary()
  results: list[CloudinaryResourceEntry] = []

  for resource_type in ('image', 'video', 'raw'):
    next_cursor: str | None = None
    while True:
      payload = cloudinary.api.resources(
        type='upload',
        prefix=prefix or None,
        max_results=500,
        next_cursor=next_cursor,
        resource_type=resource_type,
      )
      for item in payload.get('resources', []):
        results.append(
          CloudinaryResourceEntry(
            public_id=str(item.get('public_id') or ''),
            resource_type=str(item.get('resource_type') or resource_type),
            asset_type=item.get('asset_type'),
            secure_url=str(item.get('secure_url') or item.get('url') or ''),
            url=item.get('url'),
            display_name=item.get('display_name'),
            format=item.get('format'),
            bytes=item.get('bytes'),
          )
        )

      next_cursor = payload.get('next_cursor')
      if not next_cursor:
        break

  return results


def load_db_references() -> dict[str, object]:
  with engine.connect() as conn:
    media_rows = conn.execute(
      text(
        '''
        SELECT id, title, file_name, COALESCE(url, '') AS url, storage_path
        FROM media_assets
        ORDER BY id
        '''
      )
    ).mappings().all()

    product_rows = conn.execute(
      text(
        '''
        SELECT id, slug, name, COALESCE(image_url, '') AS image_url
        FROM products
        ORDER BY id
        '''
      )
    ).mappings().all()

    product_image_rows = conn.execute(
      text(
        '''
        SELECT pi.id, pi.product_id, COALESCE(pi.url, '') AS url, p.slug, p.name
        FROM product_images pi
        LEFT JOIN products p ON p.id = pi.product_id
        ORDER BY pi.id
        '''
      )
    ).mappings().all()

  media_assets = [
    MediaAssetRecord(
      media_id=int(row['id']),
      title=row.get('title'),
      file_name=row.get('file_name'),
      url=normalize_text(row.get('url')),
      storage_path=row.get('storage_path'),
    )
    for row in media_rows
  ]

  db_url_refs: list[DbUrlReference] = []
  for row in product_rows:
    url = normalize_text(row.get('image_url'))
    if not url:
      continue
    db_url_refs.append(
      DbUrlReference(
        source='products.image_url',
        record_id=int(row['id']),
        product_id=int(row['id']),
        product_slug=row.get('slug'),
        product_name=row.get('name'),
        url=url,
        public_id_guess=extract_public_id_from_cloudinary_url(url),
      )
    )

  for row in product_image_rows:
    url = normalize_text(row.get('url'))
    if not url:
      continue
    db_url_refs.append(
      DbUrlReference(
        source='product_images.url',
        record_id=int(row['id']),
        product_id=int(row['product_id']) if row.get('product_id') is not None else None,
        product_slug=row.get('slug'),
        product_name=row.get('name'),
        url=url,
        public_id_guess=extract_public_id_from_cloudinary_url(url),
      )
    )

  return {
    'media_assets': media_assets,
    'db_url_refs': db_url_refs,
  }


def audit_alignment(prefix: str | None = None) -> dict[str, object]:
  db_payload = load_db_references()
  media_assets: list[MediaAssetRecord] = db_payload['media_assets']
  db_url_refs: list[DbUrlReference] = db_payload['db_url_refs']

  resources = fetch_cloudinary_resources(prefix=prefix)

  cloud_by_public_id = {item.public_id: item for item in resources if item.public_id}
  cloud_by_url: dict[str, list[CloudinaryResourceEntry]] = defaultdict(list)
  for item in resources:
    normalized_url = normalize_cloudinary_url(item.secure_url)
    if normalized_url:
      cloud_by_url[normalized_url].append(item)
    normalized_fallback_url = normalize_cloudinary_url(item.url)
    if normalized_fallback_url and normalized_fallback_url != normalized_url:
      cloud_by_url[normalized_fallback_url].append(item)

  cloudinary_prefix = normalize_text(prefix or settings.cloudinary_folder).lower()
  media_cloudinary = [
    item
    for item in media_assets
    if (
      'res.cloudinary.com/' in normalize_text(item.url)
      or normalize_text(item.storage_path).lower().startswith(f'{cloudinary_prefix}/')
    )
  ]
  media_by_public_id = {
    normalize_text(item.storage_path): item
    for item in media_cloudinary
    if normalize_text(item.storage_path)
  }
  media_by_url: dict[str, list[MediaAssetRecord]] = defaultdict(list)
  for item in media_cloudinary:
    normalized = normalize_cloudinary_url(item.url)
    if normalized:
      media_by_url[normalized].append(item)

  cloudinary_missing_in_media_assets = []
  for resource in resources:
    normalized_url = normalize_cloudinary_url(resource.secure_url)
    if resource.public_id not in media_by_public_id and not media_by_url.get(normalized_url):
      cloudinary_missing_in_media_assets.append(asdict(resource))

  media_assets_missing_on_cloudinary = []
  for item in media_cloudinary:
    storage_path = normalize_text(item.storage_path)
    normalized_url = normalize_cloudinary_url(item.url)
    exists_on_cloud = False
    if storage_path and storage_path in cloud_by_public_id:
      exists_on_cloud = True
    elif normalized_url and cloud_by_url.get(normalized_url):
      exists_on_cloud = True

    if not exists_on_cloud:
      media_assets_missing_on_cloudinary.append(
        {
          'media_id': item.media_id,
          'title': item.title,
          'file_name': item.file_name,
          'url': item.url,
          'storage_path': item.storage_path,
        }
      )

  db_refs_without_media_asset = []
  db_refs_missing_on_cloudinary = []
  for ref in db_url_refs:
    normalized_url = normalize_cloudinary_url(ref.url)
    linked_media = media_by_url.get(normalized_url, []) if normalized_url else []
    linked_cloud = cloud_by_url.get(normalized_url, []) if normalized_url else []
    public_id_guess = normalize_text(ref.public_id_guess)

    if not linked_media and not (public_id_guess and public_id_guess in media_by_public_id):
      db_refs_without_media_asset.append(asdict(ref))

    exists_on_cloud = bool(linked_cloud) or bool(public_id_guess and public_id_guess in cloud_by_public_id)
    if not exists_on_cloud:
      db_refs_missing_on_cloudinary.append(asdict(ref))

  duplicate_media_asset_public_ids = []
  public_id_counts: dict[str, list[int]] = defaultdict(list)
  for item in media_cloudinary:
    public_id = normalize_text(item.storage_path)
    if public_id:
      public_id_counts[public_id].append(item.media_id)
  for public_id, ids in public_id_counts.items():
    if len(ids) > 1:
      duplicate_media_asset_public_ids.append({'public_id': public_id, 'media_ids': ids})

  return {
    'summary': {
      'database_url': settings.database_url,
      'media_storage': settings.media_storage,
      'cloudinary_folder': settings.cloudinary_folder,
      'cloudinary_prefix_checked': prefix or '',
      'media_assets_total': len(media_assets),
      'media_assets_cloudinary_total': len(media_cloudinary),
      'product_url_refs_total': len(db_url_refs),
      'cloudinary_resources_total': len(resources),
      'cloudinary_missing_in_media_assets_total': len(cloudinary_missing_in_media_assets),
      'media_assets_missing_on_cloudinary_total': len(media_assets_missing_on_cloudinary),
      'db_refs_without_media_asset_total': len(db_refs_without_media_asset),
      'db_refs_missing_on_cloudinary_total': len(db_refs_missing_on_cloudinary),
      'duplicate_media_asset_public_ids_total': len(duplicate_media_asset_public_ids),
    },
    'cloudinary_missing_in_media_assets': cloudinary_missing_in_media_assets,
    'media_assets_missing_on_cloudinary': media_assets_missing_on_cloudinary,
    'db_refs_without_media_asset': db_refs_without_media_asset,
    'db_refs_missing_on_cloudinary': db_refs_missing_on_cloudinary,
    'duplicate_media_asset_public_ids': duplicate_media_asset_public_ids,
  }


def render_markdown(report: dict[str, object]) -> str:
  summary = report['summary']

  def render_rows(title: str, rows: list[dict], columns: list[str]) -> list[str]:
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

  lines = [
    '# Đối chiếu Cloudinary ↔ DB',
    '',
    '## Tóm tắt',
    '',
    f"- Database URL: `{summary.get('database_url', '')}`",
    f"- Media storage: `{summary.get('media_storage', '')}`",
    f"- Cloudinary folder: `{summary.get('cloudinary_folder', '')}`",
    f"- Prefix kiểm tra: `{summary.get('cloudinary_prefix_checked', '')}`",
    f"- Tổng media_assets: **{summary.get('media_assets_total', 0)}**",
    f"- media_assets dùng Cloudinary: **{summary.get('media_assets_cloudinary_total', 0)}**",
    f"- Tổng URL tham chiếu trong products/product_images: **{summary.get('product_url_refs_total', 0)}**",
    f"- Tổng resource lấy từ Cloudinary: **{summary.get('cloudinary_resources_total', 0)}**",
    f"- Cloudinary có file nhưng media_assets chưa có: **{summary.get('cloudinary_missing_in_media_assets_total', 0)}**",
    f"- media_assets trỏ Cloudinary nhưng file không còn trên Cloudinary: **{summary.get('media_assets_missing_on_cloudinary_total', 0)}**",
    f"- products/product_images có URL nhưng không map tới media_assets: **{summary.get('db_refs_without_media_asset_total', 0)}**",
    f"- products/product_images có URL nhưng Cloudinary không còn file: **{summary.get('db_refs_missing_on_cloudinary_total', 0)}**",
    f"- public_id trùng trong media_assets: **{summary.get('duplicate_media_asset_public_ids_total', 0)}**",
  ]

  lines.extend(
    render_rows(
      'Cloudinary có file nhưng media_assets chưa ghi nhận',
      report['cloudinary_missing_in_media_assets'],
      ['public_id', 'display_name', 'secure_url', 'resource_type', 'format'],
    )
  )
  lines.extend(
    render_rows(
      'media_assets trỏ file Cloudinary không còn tồn tại',
      report['media_assets_missing_on_cloudinary'],
      ['media_id', 'title', 'file_name', 'storage_path', 'url'],
    )
  )
  lines.extend(
    render_rows(
      'URL trong products/product_images chưa map tới media_assets',
      report['db_refs_without_media_asset'],
      ['source', 'record_id', 'product_id', 'product_slug', 'url', 'public_id_guess'],
    )
  )
  lines.extend(
    render_rows(
      'URL trong products/product_images không còn file trên Cloudinary',
      report['db_refs_missing_on_cloudinary'],
      ['source', 'record_id', 'product_id', 'product_slug', 'url', 'public_id_guess'],
    )
  )
  lines.extend(
    render_rows(
      'public_id bị trùng trong media_assets',
      report['duplicate_media_asset_public_ids'],
      ['public_id', 'media_ids'],
    )
  )

  return '\n'.join(lines)


def write_report(report: dict[str, object], json_output: Path, md_output: Path) -> None:
  json_output.parent.mkdir(parents=True, exist_ok=True)
  md_output.parent.mkdir(parents=True, exist_ok=True)
  json_output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
  md_output.write_text(render_markdown(report), encoding='utf-8')


def main() -> None:
  parser = argparse.ArgumentParser(description='Đối chiếu file ảnh giữa Cloudinary và DB.')
  parser.add_argument('--prefix', default=settings.cloudinary_folder.strip())
  parser.add_argument('--json-output', default=str(DEFAULT_JSON_OUTPUT))
  parser.add_argument('--md-output', default=str(DEFAULT_MD_OUTPUT))
  args = parser.parse_args()

  report = audit_alignment(prefix=args.prefix)
  json_output = Path(args.json_output)
  md_output = Path(args.md_output)
  write_report(report, json_output=json_output, md_output=md_output)

  summary = report['summary']
  print(f"[OK] JSON report: {json_output}")
  print(f"[OK] Markdown report: {md_output}")
  print(
    '[SUMMARY] cloudinary_resources={cloudinary_resources} media_assets_cloudinary={media_assets_cloudinary} db_refs_without_media_asset={db_refs_without_media_asset} db_refs_missing_on_cloudinary={db_refs_missing_on_cloudinary}'.format(
      cloudinary_resources=summary.get('cloudinary_resources_total', 0),
      media_assets_cloudinary=summary.get('media_assets_cloudinary_total', 0),
      db_refs_without_media_asset=summary.get('db_refs_without_media_asset_total', 0),
      db_refs_missing_on_cloudinary=summary.get('db_refs_missing_on_cloudinary_total', 0),
    )
  )


if __name__ == '__main__':
  main()
