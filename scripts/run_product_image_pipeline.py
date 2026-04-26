from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
  sys.path.insert(0, str(PROJECT_ROOT))

from scripts.audit_product_image_system import build_report as build_audit_report
from scripts.import_missing_product_images_csv import build_report as build_import_report
from scripts.validate_missing_product_images_csv import build_report as build_validate_report

DEFAULT_CSV_INPUT = PROJECT_ROOT / 'scripts' / 'reports' / 'missing_product_images_template.csv'
DEFAULT_JSON_OUTPUT = PROJECT_ROOT / 'scripts' / 'reports' / 'product_image_pipeline.json'
DEFAULT_MD_OUTPUT = PROJECT_ROOT / 'scripts' / 'reports' / 'product_image_pipeline.md'
DEFAULT_CLOUDINARY_PREFIX = 'China_web'


def parse_args() -> argparse.Namespace:
  parser = argparse.ArgumentParser(
    description='Pipeline tổng validate -> import -> audit cho hệ thống ảnh sản phẩm.',
  )
  parser.add_argument('--csv-input', default=str(DEFAULT_CSV_INPUT))
  parser.add_argument('--execute', action='store_true', help='Cho phép chạy bước import thật sau khi validate đạt điều kiện.')
  parser.add_argument(
    '--allow-warn-import',
    action='store_true',
    help='Cho phép import ngay cả khi validate có WARN. Mặc định chỉ import khi validate PASS.',
  )
  parser.add_argument('--prefix', default=DEFAULT_CLOUDINARY_PREFIX)
  parser.add_argument('--json-output', default=str(DEFAULT_JSON_OUTPUT))
  parser.add_argument('--md-output', default=str(DEFAULT_MD_OUTPUT))
  return parser.parse_args()


def determine_import_gate(validate_report: dict[str, Any], *, execute: bool, allow_warn_import: bool) -> dict[str, Any]:
  validate_summary = validate_report.get('summary', {})
  validate_status = str(validate_summary.get('overall_status', 'FAIL')).upper()

  if not execute:
    return {
      'can_import': False,
      'import_attempted': False,
      'import_mode': 'dry-run',
      'reason': 'Pipeline đang chạy ở dry-run nên không thực hiện import DB.',
    }

  if validate_status == 'FAIL':
    return {
      'can_import': False,
      'import_attempted': False,
      'import_mode': 'execute',
      'reason': 'Validate đang FAIL nên pipeline chặn import để bảo vệ dữ liệu.',
    }

  if validate_status == 'WARN' and not allow_warn_import:
    return {
      'can_import': False,
      'import_attempted': False,
      'import_mode': 'execute',
      'reason': 'Validate đang WARN. Thêm --allow-warn-import nếu bạn vẫn muốn import.',
    }

  return {
    'can_import': True,
    'import_attempted': True,
    'import_mode': 'execute',
    'reason': 'Validate đạt điều kiện cho phép import.',
  }


def build_pipeline_report(
  *,
  csv_input: Path,
  execute: bool,
  allow_warn_import: bool,
  prefix: str,
) -> dict[str, Any]:
  validate_report = build_validate_report(csv_input)
  import_gate = determine_import_gate(
    validate_report,
    execute=execute,
    allow_warn_import=allow_warn_import,
  )
  import_report = build_import_report(
    csv_input=csv_input,
    execute=bool(import_gate['can_import']),
  )
  audit_report = build_audit_report(prefix=prefix)

  validate_summary = validate_report.get('summary', {})
  import_summary = import_report.get('summary', {})
  audit_summary = audit_report.get('summary', {})
  audit_product_summary = audit_report.get('product_summary', {})

  pipeline_status = 'PASS'
  if str(validate_summary.get('overall_status', 'PASS')).upper() == 'FAIL':
    pipeline_status = 'FAIL'
  elif str(audit_report.get('health_status', 'PASS')).upper() == 'FAIL':
    pipeline_status = 'FAIL'
  elif str(validate_summary.get('overall_status', 'PASS')).upper() == 'WARN' or str(audit_report.get('health_status', 'PASS')).upper() == 'WARN':
    pipeline_status = 'WARN'

  return {
    'summary': {
      'pipeline_status': pipeline_status,
      'csv_input': str(csv_input),
      'execute_requested': execute,
      'allow_warn_import': allow_warn_import,
      'import_attempted': bool(import_gate['import_attempted']),
      'import_executed': bool(import_gate['can_import']),
      'import_gate_reason': import_gate['reason'],
      'validate_status': validate_summary.get('overall_status', 'UNKNOWN'),
      'validate_pass_total': validate_summary.get('pass_total', 0),
      'validate_warn_total': validate_summary.get('warn_total', 0),
      'validate_fail_total': validate_summary.get('fail_total', 0),
      'import_ready_total': import_summary.get('ready_total', 0),
      'import_updated_total': import_summary.get('updated_total', 0),
      'import_skipped_total': import_summary.get('skipped_total', 0),
      'audit_health_status': audit_report.get('health_status', 'UNKNOWN'),
      'audit_products_missing_primary_total': audit_product_summary.get('products_missing_primary_total', 0),
      'audit_products_without_any_image_total': audit_product_summary.get('products_without_any_image_total', 0),
      'audit_db_refs_without_media_asset_total': audit_summary.get('db_refs_without_media_asset_total', 0),
      'audit_db_refs_missing_on_cloudinary_total': audit_summary.get('db_refs_missing_on_cloudinary_total', 0),
    },
    'validate': validate_report,
    'import': import_report,
    'audit': audit_report,
  }


def render_markdown(report: dict[str, Any]) -> str:
  summary = report['summary']
  lines = [
    '# Pipeline tổng ảnh sản phẩm',
    '',
    '## Tóm tắt',
    '',
    f"- Pipeline status: **{summary.get('pipeline_status', 'UNKNOWN')}**",
    f"- CSV input: `{summary.get('csv_input', '')}`",
    f"- Execute requested: **{summary.get('execute_requested', False)}**",
    f"- Allow warn import: **{summary.get('allow_warn_import', False)}**",
    f"- Import attempted: **{summary.get('import_attempted', False)}**",
    f"- Import executed: **{summary.get('import_executed', False)}**",
    f"- Import gate reason: {summary.get('import_gate_reason', '')}",
    '',
    '## Kết quả validate',
    '',
    f"- Validate status: **{summary.get('validate_status', 'UNKNOWN')}**",
    f"- PASS: **{summary.get('validate_pass_total', 0)}**",
    f"- WARN: **{summary.get('validate_warn_total', 0)}**",
    f"- FAIL: **{summary.get('validate_fail_total', 0)}**",
    '',
    '## Kết quả import',
    '',
    f"- Ready: **{summary.get('import_ready_total', 0)}**",
    f"- Updated: **{summary.get('import_updated_total', 0)}**",
    f"- Skipped: **{summary.get('import_skipped_total', 0)}**",
    '',
    '## Kết quả audit cuối',
    '',
    f"- Audit health: **{summary.get('audit_health_status', 'UNKNOWN')}**",
    f"- Sản phẩm thiếu ảnh chính: **{summary.get('audit_products_missing_primary_total', 0)}**",
    f"- Sản phẩm thiếu hoàn toàn ảnh: **{summary.get('audit_products_without_any_image_total', 0)}**",
    f"- DB refs chưa map media_assets: **{summary.get('audit_db_refs_without_media_asset_total', 0)}**",
    f"- DB refs mất file trên Cloudinary: **{summary.get('audit_db_refs_missing_on_cloudinary_total', 0)}**",
    '',
    '## Hướng dẫn dùng',
    '',
    '- Dry-run tổng: `python scripts/run_product_image_pipeline.py`',
    '- Execute an toàn khi validate PASS: `python scripts/run_product_image_pipeline.py --execute`',
    '- Execute cả khi validate WARN: `python scripts/run_product_image_pipeline.py --execute --allow-warn-import`',
    '',
    '## File report chi tiết',
    '',
    '- Validate chi tiết nằm trong phần `validate` của JSON pipeline.',
    '- Import chi tiết nằm trong phần `import` của JSON pipeline.',
    '- Audit chi tiết nằm trong phần `audit` của JSON pipeline.',
  ]
  return '\n'.join(lines)


def write_outputs(report: dict[str, Any], *, json_output: Path, md_output: Path) -> None:
  json_output.parent.mkdir(parents=True, exist_ok=True)
  md_output.parent.mkdir(parents=True, exist_ok=True)
  json_output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
  md_output.write_text(render_markdown(report), encoding='utf-8')


def main() -> None:
  args = parse_args()
  csv_input = Path(args.csv_input)
  report = build_pipeline_report(
    csv_input=csv_input,
    execute=args.execute,
    allow_warn_import=args.allow_warn_import,
    prefix=args.prefix,
  )
  json_output = Path(args.json_output)
  md_output = Path(args.md_output)
  write_outputs(report, json_output=json_output, md_output=md_output)

  print(f'[OK] JSON report: {json_output}')
  print(f'[OK] Markdown report: {md_output}')
  print(
    '[SUMMARY] pipeline={pipeline} validate={validate} import_executed={import_executed} updated={updated} audit={audit}'.format(
      pipeline=report['summary'].get('pipeline_status', 'UNKNOWN'),
      validate=report['summary'].get('validate_status', 'UNKNOWN'),
      import_executed=report['summary'].get('import_executed', False),
      updated=report['summary'].get('import_updated_total', 0),
      audit=report['summary'].get('audit_health_status', 'UNKNOWN'),
    )
  )


if __name__ == '__main__':
  main()
