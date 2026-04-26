"""
fix_orphan_project_products.py

Script xóa các bản ghi project_products mồ côi:
- product_id trỏ tới sản phẩm không còn tồn tại trong bảng products.

Sử dụng:
  python scripts/fix_orphan_project_products.py                      # dry-run
  python scripts/fix_orphan_project_products.py --apply              # thực thi xóa
  python scripts/fix_orphan_project_products.py --api-base http://...  # custom API
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

import requests


def load_backend_env() -> dict[str, str]:
    env_path = Path(__file__).resolve().parent.parent / '.env'
    values: dict[str, str] = {}
    if not env_path.exists():
        return values
    for raw_line in env_path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


class AdminClient:
    def __init__(self, api_base: str, username: str, password: str) -> None:
        self.api_base = api_base.rstrip('/')
        self.session = requests.Session()
        self.session.verify = False

        response = self.session.post(
            f'{self.api_base}/auth/login',
            json={'username': username, 'password': password},
            timeout=30,
        )
        response.raise_for_status()
        token = response.json()['access_token']
        self.session.headers.update({'Authorization': f'Bearer {token}'})

    def list_all(self, entity_name: str, **extra: Any) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        skip = 0
        limit = 100
        while True:
            resp = self.session.get(
                f'{self.api_base}/admin/{entity_name}',
                params={**extra, 'skip': skip, 'limit': limit},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            batch = data.get('items') or []
            items.extend(batch)
            if len(batch) < limit:
                break
            skip += limit
        return items

    def delete_entity(self, entity_name: str, record_id: int) -> None:
        resp = self.session.delete(
            f'{self.api_base}/admin/{entity_name}/{record_id}',
            timeout=30,
        )
        resp.raise_for_status()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Xóa bản ghi project_products mồ côi (product_id trỏ tới product không tồn tại)."
    )
    parser.add_argument('--api-base', default='https://china-be.onrender.com/api/v1', help='Backend API base URL')
    parser.add_argument('--username', default='admin', help='Admin username')
    parser.add_argument('--password', default=None, help='Admin password (hoặc đặt ADMIN_PASSWORD env var)')
    parser.add_argument('--apply', action='store_true', default=False, help='Thực thi xóa (mặc định là dry-run).')
    args = parser.parse_args()

    env_values = load_backend_env()
    password = args.password or os.getenv('ADMIN_PASSWORD') or env_values.get('ADMIN_PASSWORD', 'admin123456')

    print(f'🔗 Kết nối tới {args.api_base}...')
    client = AdminClient(args.api_base, args.username, password)
    print(f'✅ Đã đăng nhập.')

    # Lấy toàn bộ products
    products = client.list_all('products')
    product_ids = {str(p['id']) for p in products}
    print(f'📦 Tổng sản phẩm hiện hữu: {len(products)} (IDs: {sorted(int(i) for i in product_ids)})')

    # Lấy toàn bộ project_products
    pp_items = client.list_all('project_products')
    print(f'🔗 Tổng bản ghi project_products: {len(pp_items)}')

    # Tìm orphans
    orphans = [
        pp for pp in pp_items
        if str(pp.get('product_id')) not in product_ids
    ]

    if not orphans:
        print('✅ Không tìm thấy bản ghi project_products mồ côi nào. Dữ liệu sạch!')
        return

    print(f'\n⚠️  Tìm thấy {len(orphans)} bản ghi project_products mồ côi:')
    for pp in orphans:
        print(
            f'   pp.id={pp["id"]}  '
            f'project_id={pp.get("project_id")}  '
            f'product_id={pp.get("product_id")}  '
            f'product_name={pp.get("product_name")!r}'
        )

    if not args.apply:
        print(f'\n💡 Đây là DRY-RUN. Không có thay đổi nào được thực hiện.')
        print(f'   Chạy lại với --apply để xóa {len(orphans)} bản ghi mồ côi.')
        return

    print(f'\n🔧 Đang xóa {len(orphans)} bản ghi mồ côi...')
    for pp in orphans:
        client.delete_entity('project_products', int(pp['id']))
        print(f'   ✅ Đã xóa pp.id={pp["id"]} (product_id={pp.get("product_id")})')

    print(f'\n✅ Đã xóa xong {len(orphans)} bản ghi mồ côi.')
    print(f'   Bạn có thể vào trang admin để gắn lại sản phẩm cho từng dự án.')


if __name__ == '__main__':
    main()
