"""
Reset / tạo lại admin user.

Chạy:
    python scripts/reset_admin_password.py
    python scripts/reset_admin_password.py --username myuser --password MyP@ss!
"""
from pathlib import Path
import argparse
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from sqlalchemy import select
from app.db.session import SessionLocal
from app.core.security import hash_password, verify_password
from app.models.admin import AdminUser


def reset_admin(username: str, password: str) -> None:
    with SessionLocal() as session:
        user = session.scalar(select(AdminUser).where(AdminUser.username == username))

        if user:
            user.password_hash = hash_password(password)
            user.is_active = True
            session.add(user)
            session.commit()
            print(f"[OK] Password reset thành công cho user '{username}'.")
        else:
            # Tạo mới nếu chưa có
            new_user = AdminUser(
                username=username,
                password_hash=hash_password(password),
                role="admin",
                is_active=True,
            )
            session.add(new_user)
            session.commit()
            print(f"[OK] Tạo admin user mới '{username}' thành công.")

        # Xác minh lại
        refreshed = session.scalar(select(AdminUser).where(AdminUser.username == username))
        ok = verify_password(password, refreshed.password_hash)
        if ok:
            print(f"[OK] Xác minh password thành công. Bạn có thể login với: username='{username}' password='{password}'")
        else:
            print("[ERROR] Xác minh password THẤT BẠI – kiểm tra lại hàm hash_password / verify_password.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reset admin password")
    parser.add_argument("--username", default="admin", help="Admin username (mặc định: admin)")
    parser.add_argument("--password", default="admin123456", help="Password mới (mặc định: admin123456)")
    args = parser.parse_args()

    reset_admin(args.username, args.password)
