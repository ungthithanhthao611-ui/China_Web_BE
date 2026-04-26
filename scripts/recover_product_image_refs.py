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

from sqlalchemy import text

from app.db.session import engine
from app.models.products import ProductImage
from app.db.session import SessionLocal
from scripts.audit_cloudinary_db_alignment import audit_alignment

DEFAULT_JSON_OUTPUT = PROJECT_ROOT / 'scripts' / 'reports' / 'product_images_recovery_run.json'
DEFAULT_MD_OUTPUT = PROJECT_ROOT / 'scripts' / 'reports' / 'product_images_recovery_run.md'


@dataclass
class RecoveryCandidate:
    source: str
    media_id: int | None
    public_id: str | None
    url: str
    title: str | None
    score: int
    reasons: list[str]


@dataclass
class RecoveryResult:
    product_image_id: int
    product_id: int | None
    product_slug: str | None
    product_name: str | None
    broken_url: str
    broken_public_id: str | None
    status: str
    replacement_url: str | None
    replacement_public_id: str | None
    candidate_media_id: int | None
    reasons: list[str]
    error: str | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Tự động khôi phục product_images.url bị chết từ dữ liệu Cloudinary/media_assets hiện có.',
    )
    parser.add_argument('--prefix', default='China_web')
    parser.add_argument('--execute', action='store_true', help='Thực thi cập nhật DB. Mặc định chỉ dry-run.')
    parser.add_argument('--json-output', default=str(DEFAULT_JSON_OUTPUT))
    parser.add_argument('--md-output', default=str(DEFAULT_MD_OUTPUT))
    return parser.parse_args()


def normalize_text(value: Any) -> str:
    return str(value or '').strip()


def normalize_url(value: str | None) -> str:
    raw = normalize_text(value)
    if not raw:
        return ''
    parsed = urlparse(raw)
    if not parsed.scheme or not parsed.netloc:
        return raw.rstrip('/')
    return parsed._replace(query='', fragment='').geturl().rstrip('/')


def slugify(value: str | None) -> str:
    raw = normalize_text(value).lower()
    cleaned = []
    last_dash = False
    for char in raw:
        if char.isalnum():
            cleaned.append(char)
            last_dash = False
        else:
            if not last_dash:
                cleaned.append('-')
                last_dash = True
    return ''.join(cleaned).strip('-')


def extract_public_id(url: str | None) -> str | None:
    raw = normalize_text(url)
    if 'res.cloudinary.com/' not in raw:
        return None
    parsed = urlparse(raw)
    segments = [segment for segment in parsed.path.strip('/').split('/') if segment]
    if 'upload' not in segments:
        return None
    upload_index = segments.index('upload')
    tail = segments[upload_index + 1 :]
    if tail and tail[0].startswith('v') and tail[0][1:].isdigit():
        tail = tail[1:]
    if not tail:
        return None
    public_id = '/'.join(tail)
    suffix = Path(public_id).suffix
    if suffix:
        public_id = public_id[: -len(suffix)]
    return public_id or None


def path_leaf(value: str | None) -> str:
    return slugify(Path(normalize_text(value)).stem)


def load_product_context() -> dict[int, dict[str, Any]]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                '''
                SELECT id, slug, name, sku, image_url
                FROM products
                ORDER BY id
                '''
            )
        ).mappings().all()
    return {
        int(row['id']): {
            'id': int(row['id']),
            'slug': row.get('slug'),
            'name': row.get('name'),
            'sku': row.get('sku'),
            'image_url': row.get('image_url'),
        }
        for row in rows
    }


def build_cloudinary_candidates(report: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    for item in report.get('cloudinary_missing_in_media_assets', []):
        url = normalize_text(item.get('secure_url') or item.get('url'))
        normalized = normalize_url(url)
        if not normalized or normalized in seen_urls:
            continue
        seen_urls.add(normalized)
        candidates.append(
            {
                'source': 'cloudinary_only',
                'media_id': None,
                'public_id': item.get('public_id'),
                'url': url,
                'title': item.get('display_name'),
            }
        )

    with engine.connect() as conn:
        media_rows = conn.execute(
            text(
                '''
                SELECT id, title, file_name, url, storage_path
                FROM media_assets
                WHERE COALESCE(url, '') <> ''
                ORDER BY id
                '''
            )
        ).mappings().all()

    for row in media_rows:
        url = normalize_text(row.get('url'))
        normalized = normalize_url(url)
        if not normalized or normalized in seen_urls:
            continue
        seen_urls.add(normalized)
        candidates.append(
            {
                'source': 'media_assets',
                'media_id': int(row['id']),
                'public_id': row.get('storage_path') or extract_public_id(url),
                'url': url,
                'title': row.get('title') or row.get('file_name'),
            }
        )

    return candidates


def score_candidate(broken: dict[str, Any], product: dict[str, Any], candidate: dict[str, Any]) -> RecoveryCandidate | None:
    product_slug = slugify(product.get('slug'))
    product_name_slug = slugify(product.get('name'))
    product_sku_slug = slugify(product.get('sku'))
    broken_leaf = path_leaf(broken.get('broken_public_id') or broken.get('broken_url'))
    candidate_public_id = normalize_text(candidate.get('public_id'))
    candidate_url = normalize_text(candidate.get('url'))
    candidate_title = normalize_text(candidate.get('title'))
    candidate_leaf = path_leaf(candidate_public_id or candidate_url)
    candidate_lower = ' '.join(
        value
        for value in [candidate_public_id.lower(), candidate_url.lower(), candidate_title.lower()]
        if value
    )

    score = 0
    reasons: list[str] = []

    if not candidate_url:
        return None

    if product_slug and product_slug in candidate_lower:
        score += 80
        reasons.append(f'Khớp slug sản phẩm: {product_slug}')
    if product_name_slug and product_name_slug in candidate_lower:
        score += 40
        reasons.append(f'Khớp tên sản phẩm: {product_name_slug}')
    if product_sku_slug and product_sku_slug in candidate_lower:
        score += 35
        reasons.append(f'Khớp SKU: {product_sku_slug}')
    if broken_leaf and candidate_leaf and broken_leaf == candidate_leaf:
        score += 120
        reasons.append(f'Khớp tên file/public_id gốc: {broken_leaf}')
    elif broken_leaf and candidate_leaf and broken_leaf in candidate_leaf:
        score += 70
        reasons.append(f'Leaf gần giống ảnh gốc: {candidate_leaf}')

    if product_slug and candidate_public_id.lower().startswith(f'china_web/products/{product_slug}'):
        score += 60
        reasons.append('Nằm đúng thư mục sản phẩm chuẩn trên Cloudinary')
    elif candidate_public_id.lower().startswith('china_web/products/'):
        score += 20
        reasons.append('Thuộc namespace products chuẩn')

    if candidate.get('source') == 'media_assets':
        score += 15
        reasons.append('Có record media_assets đồng bộ DB')

    if score <= 0:
        return None

    return RecoveryCandidate(
        source=str(candidate.get('source')),
        media_id=candidate.get('media_id'),
        public_id=candidate.get('public_id'),
        url=candidate_url,
        title=candidate.get('title'),
        score=score,
        reasons=reasons,
    )


def choose_best_candidate(
    broken: dict[str, Any],
    product: dict[str, Any],
    candidates: list[dict[str, Any]],
) -> RecoveryCandidate | None:
    scored = [
        score_candidate(broken, product, candidate)
        for candidate in candidates
    ]
    valid = [candidate for candidate in scored if candidate is not None]
    if not valid:
        return None
    valid.sort(
        key=lambda item: (
            item.score,
            1 if item.source == 'media_assets' else 0,
            len(normalize_text(item.public_id)),
        ),
        reverse=True,
    )
    top = valid[0]
    if top.score < 60:
        return None
    return top


def build_recovery_plan(prefix: str) -> dict[str, Any]:
    report = audit_alignment(prefix=prefix)
    broken_refs = [
        item
        for item in report.get('db_refs_missing_on_cloudinary', [])
        if item.get('source') == 'product_images.url'
    ]
    products = load_product_context()
    candidates = build_cloudinary_candidates(report)
    results: list[RecoveryResult] = []

    for broken in broken_refs:
        product_id = broken.get('product_id')
        product = products.get(int(product_id)) if product_id is not None and int(product_id) in products else {
            'slug': broken.get('product_slug'),
            'name': broken.get('product_name'),
            'sku': None,
        }
        best = choose_best_candidate(broken, product, candidates)
        if not best:
            results.append(
                RecoveryResult(
                    product_image_id=int(broken['record_id']),
                    product_id=product_id,
                    product_slug=product.get('slug'),
                    product_name=product.get('name'),
                    broken_url=broken.get('url') or '',
                    broken_public_id=broken.get('public_id_guess'),
                    status='needs_manual_review',
                    replacement_url=None,
                    replacement_public_id=None,
                    candidate_media_id=None,
                    reasons=['Không tìm được ứng viên đủ tin cậy từ Cloudinary/media_assets.'],
                )
            )
            continue

        results.append(
            RecoveryResult(
                product_image_id=int(broken['record_id']),
                product_id=product_id,
                product_slug=product.get('slug'),
                product_name=product.get('name'),
                broken_url=broken.get('url') or '',
                broken_public_id=broken.get('public_id_guess'),
                status='ready',
                replacement_url=best.url,
                replacement_public_id=best.public_id,
                candidate_media_id=best.media_id,
                reasons=[f'Score={best.score}', *best.reasons],
            )
        )

    return {
        'audit_summary': report.get('summary', {}),
        'results': [asdict(item) for item in results],
    }


def execute_recovery(plan: dict[str, Any]) -> dict[str, Any]:
    results = plan.get('results', [])
    executed: list[dict[str, Any]] = []

    with SessionLocal() as session:
        for item in results:
            current = dict(item)
            if current.get('status') != 'ready' or not current.get('replacement_url'):
                executed.append(current)
                continue
            try:
                record = session.get(ProductImage, int(current['product_image_id']))
                if not record:
                    current['status'] = 'failed'
                    current['error'] = 'Không tìm thấy product_images record để cập nhật.'
                else:
                    record.url = str(current['replacement_url']).strip()
                    session.add(record)
                    session.flush()
                    current['status'] = 'recovered'
            except Exception as exc:  # noqa: BLE001
                session.rollback()
                current['status'] = 'failed'
                current['error'] = str(exc)
            executed.append(current)
        session.commit()

    plan['results'] = executed
    return plan


def render_markdown(report: dict[str, Any], execute: bool) -> str:
    summary = report.get('audit_summary', {})
    results = report.get('results', [])
    lines = [
        '# Kết quả khôi phục product_images bị chết',
        '',
        '## Tóm tắt đầu vào',
        '',
        f"- Chế độ: **{'execute' if execute else 'dry_run'}**",
        f"- Prefix audit: `{summary.get('cloudinary_prefix_checked', '')}`",
        f"- product_images URL chết theo audit: **{summary.get('db_refs_missing_on_cloudinary_total', 0)}**",
        f"- Tổng item recovery: **{len(results)}**",
        f"- Có thể auto-fix: **{sum(1 for item in results if item.get('status') in {'ready', 'recovered'})}**",
        f"- Cần review tay: **{sum(1 for item in results if item.get('status') == 'needs_manual_review')}**",
        f"- Lỗi khi execute: **{sum(1 for item in results if item.get('status') == 'failed')}**",
        '',
        '## Chi tiết',
        '',
        '| product_image_id | product_id | product_slug | status | broken_public_id | replacement_public_id | candidate_media_id | reasons | error |',
        '| --- | --- | --- | --- | --- | --- | --- | --- | --- |',
    ]

    for item in results:
        lines.append(
            '| {product_image_id} | {product_id} | {product_slug} | {status} | {broken_public_id} | {replacement_public_id} | {candidate_media_id} | {reasons} | {error} |'.format(
                product_image_id=item.get('product_image_id', ''),
                product_id=item.get('product_id', ''),
                product_slug=str(item.get('product_slug') or '').replace('|', '\\|'),
                status=item.get('status', ''),
                broken_public_id=str(item.get('broken_public_id') or '').replace('|', '\\|'),
                replacement_public_id=str(item.get('replacement_public_id') or '').replace('|', '\\|'),
                candidate_media_id=item.get('candidate_media_id', ''),
                reasons='; '.join(item.get('reasons', [])).replace('|', '\\|'),
                error=str(item.get('error') or '').replace('|', '\\|'),
            )
        )

    return '\n'.join(lines)


def write_report(report: dict[str, Any], *, execute: bool, json_output: Path, md_output: Path) -> None:
    json_output.parent.mkdir(parents=True, exist_ok=True)
    md_output.parent.mkdir(parents=True, exist_ok=True)
    json_output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    md_output.write_text(render_markdown(report, execute=execute), encoding='utf-8')


def main() -> None:
    args = parse_args()
    plan = build_recovery_plan(prefix=args.prefix)
    if args.execute:
        plan = execute_recovery(plan)

    json_output = Path(args.json_output)
    md_output = Path(args.md_output)
    write_report(plan, execute=args.execute, json_output=json_output, md_output=md_output)

    results = plan.get('results', [])
    print(f'[OK] JSON report: {json_output}')
    print(f'[OK] Markdown report: {md_output}')
    print(
        '[SUMMARY] mode={mode} total={total} auto_fixable={auto_fixable} manual_review={manual_review} failed={failed}'.format(
            mode='execute' if args.execute else 'dry_run',
            total=len(results),
            auto_fixable=sum(1 for item in results if item.get('status') in {'ready', 'recovered'}),
            manual_review=sum(1 for item in results if item.get('status') == 'needs_manual_review'),
            failed=sum(1 for item in results if item.get('status') == 'failed'),
        )
    )


if __name__ == '__main__':
    main()
