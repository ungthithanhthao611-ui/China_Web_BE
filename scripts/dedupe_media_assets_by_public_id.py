from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import text

from app.db.session import SessionLocal, engine
from app.services.media import _media_asset_references

DEFAULT_JSON_OUTPUT = PROJECT_ROOT / 'scripts' / 'reports' / 'media_assets_dedupe_run.json'
DEFAULT_MD_OUTPUT = PROJECT_ROOT / 'scripts' / 'reports' / 'media_assets_dedupe_run.md'


@dataclass
class DedupeDecision:
    public_id: str
    keep_media_id: int | None
    delete_media_ids: list[int]
    status: str
    reasons: list[str]
    blocked_media_ids: list[int]
    error: str | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Dọn record media_assets bị trùng public_id một cách an toàn.')
    parser.add_argument('--execute', action='store_true', help='Thực thi xóa record trùng. Mặc định chỉ dry-run.')
    parser.add_argument('--json-output', default=str(DEFAULT_JSON_OUTPUT))
    parser.add_argument('--md-output', default=str(DEFAULT_MD_OUTPUT))
    return parser.parse_args()


def normalize_text(value: Any) -> str:
    return str(value or '').strip()


def fetch_duplicate_groups() -> list[dict[str, Any]]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                '''
                SELECT
                  storage_path AS public_id,
                  ARRAY_AGG(id ORDER BY id) AS media_ids
                FROM media_assets
                WHERE COALESCE(storage_path, '') <> ''
                GROUP BY storage_path
                HAVING COUNT(*) > 1
                ORDER BY storage_path
                '''
            )
        ).mappings().all()

        media_rows = conn.execute(
            text(
                '''
                SELECT id, storage_path, url, title, file_name, width, height, size, created_at
                FROM media_assets
                WHERE COALESCE(storage_path, '') <> ''
                ORDER BY id
                '''
            )
        ).mappings().all()

    media_index = {int(row['id']): dict(row) for row in media_rows}
    groups: list[dict[str, Any]] = []
    for row in rows:
        ids = [int(media_id) for media_id in row.get('media_ids') or []]
        groups.append(
            {
                'public_id': row.get('public_id'),
                'records': [media_index[media_id] for media_id in ids if media_id in media_index],
            }
        )
    return groups


def reference_count(session, media_id: int) -> tuple[int, list[str]]:
    refs = _media_asset_references(session, media_id)
    return len(refs), refs


def quality_score(record: dict[str, Any]) -> int:
    score = 0
    if normalize_text(record.get('url')).startswith('https://'):
        score += 10
    if record.get('width'):
        score += 5
    if record.get('height'):
        score += 5
    if record.get('size'):
        score += 5
    if normalize_text(record.get('title')):
        score += 3
    if normalize_text(record.get('file_name')):
        score += 2
    return score


def plan_dedupe() -> dict[str, Any]:
    groups = fetch_duplicate_groups()
    decisions: list[DedupeDecision] = []

    with SessionLocal() as session:
        for group in groups:
            public_id = normalize_text(group.get('public_id'))
            records = group.get('records', [])
            enriched = []
            for record in records:
                count, refs = reference_count(session, int(record['id']))
                enriched.append(
                    {
                        **record,
                        'ref_count': count,
                        'refs': refs,
                        'quality_score': quality_score(record),
                    }
                )

            enriched.sort(
                key=lambda item: (
                    item['ref_count'],
                    item['quality_score'],
                    -int(item['id']),
                ),
                reverse=True,
            )

            keeper = enriched[0] if enriched else None
            blocked_media_ids = [int(item['id']) for item in enriched[1:] if item['ref_count'] > 0]
            delete_media_ids = [int(item['id']) for item in enriched[1:] if item['ref_count'] == 0]
            reasons = []

            if keeper:
                reasons.append(
                    f"Giữ media_id={keeper['id']} vì ref_count={keeper['ref_count']} và quality_score={keeper['quality_score']}"
                )
            if delete_media_ids:
                reasons.append(f'Có thể xóa an toàn các media_id không còn tham chiếu: {delete_media_ids}')
            if blocked_media_ids:
                reasons.append(f'Chưa xóa các media_id còn tham chiếu: {blocked_media_ids}')

            status = 'ready' if delete_media_ids else 'blocked'
            decisions.append(
                DedupeDecision(
                    public_id=public_id,
                    keep_media_id=int(keeper['id']) if keeper else None,
                    delete_media_ids=delete_media_ids,
                    status=status,
                    reasons=reasons or ['Không có bản ghi đủ điều kiện để xóa.'],
                    blocked_media_ids=blocked_media_ids,
                )
            )

    return {'decisions': [asdict(item) for item in decisions]}


def execute_dedupe(plan: dict[str, Any]) -> dict[str, Any]:
    decisions = plan.get('decisions', [])
    updated: list[dict[str, Any]] = []

    with SessionLocal() as session:
        for decision in decisions:
            current = dict(decision)
            if current.get('status') != 'ready':
                updated.append(current)
                continue
            try:
                delete_ids = [int(media_id) for media_id in current.get('delete_media_ids', [])]
                if delete_ids:
                    session.execute(
                        text('DELETE FROM media_assets WHERE id = ANY(:ids)'),
                        {'ids': delete_ids},
                    )
                    session.flush()
                current['status'] = 'deleted'
            except Exception as exc:  # noqa: BLE001
                session.rollback()
                current['status'] = 'failed'
                current['error'] = str(exc)
            updated.append(current)
        session.commit()

    plan['decisions'] = updated
    return plan


def render_markdown(report: dict[str, Any], execute: bool) -> str:
    decisions = report.get('decisions', [])
    lines = [
        '# Kết quả dọn trùng media_assets',
        '',
        f"- Chế độ: **{'execute' if execute else 'dry_run'}**",
        f"- Tổng nhóm public_id bị trùng: **{len(decisions)}**",
        f"- Sẵn sàng xóa: **{sum(1 for item in decisions if item.get('status') in {'ready', 'deleted'})}**",
        f"- Bị chặn do còn tham chiếu: **{sum(1 for item in decisions if item.get('status') == 'blocked')}**",
        f"- Lỗi khi execute: **{sum(1 for item in decisions if item.get('status') == 'failed')}**",
        '',
        '| public_id | keep_media_id | delete_media_ids | blocked_media_ids | status | reasons | error |',
        '| --- | --- | --- | --- | --- | --- | --- |',
    ]

    for item in decisions:
        lines.append(
            '| {public_id} | {keep_media_id} | {delete_media_ids} | {blocked_media_ids} | {status} | {reasons} | {error} |'.format(
                public_id=str(item.get('public_id') or '').replace('|', '\\|'),
                keep_media_id=item.get('keep_media_id', ''),
                delete_media_ids=item.get('delete_media_ids', []),
                blocked_media_ids=item.get('blocked_media_ids', []),
                status=item.get('status', ''),
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
    plan = plan_dedupe()
    if args.execute:
        plan = execute_dedupe(plan)

    json_output = Path(args.json_output)
    md_output = Path(args.md_output)
    write_report(plan, execute=args.execute, json_output=json_output, md_output=md_output)

    decisions = plan.get('decisions', [])
    print(f'[OK] JSON report: {json_output}')
    print(f'[OK] Markdown report: {md_output}')
    print(
        '[SUMMARY] mode={mode} total={total} ready={ready} blocked={blocked} failed={failed}'.format(
            mode='execute' if args.execute else 'dry_run',
            total=len(decisions),
            ready=sum(1 for item in decisions if item.get('status') in {'ready', 'deleted'}),
            blocked=sum(1 for item in decisions if item.get('status') == 'blocked'),
            failed=sum(1 for item in decisions if item.get('status') == 'failed'),
        )
    )


if __name__ == '__main__':
    main()
