"""
Script cap nhat kich thuoc san pham:
- Gach the (OS.16) & Gach the co dien (OS.17): 60x240mm
- Tat ca san pham con lai: 600x1200mm
"""
import sys
import os
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("[ERROR] Khong tim thay DATABASE_URL trong .env")
    sys.exit(1)

engine = create_engine(DATABASE_URL)

# Kich thuoc cho gach the
GACH_THE_SIZE = "60x240mm (Kích thước mẫu)"
GACH_THE_SIZE_EN = "60x240mm (Sample size)"
GACH_THE_SIZE_ZH = "60x240mm（样品尺寸）"

# Kich thuoc cho cac san pham con lai
DEFAULT_SIZE = "600x1200mm (Kích thước mẫu)"
DEFAULT_SIZE_EN = "600x1200mm (Sample size)"
DEFAULT_SIZE_ZH = "600x1200mm（样品尺寸）"

with engine.begin() as conn:
    # 1. Cap nhat gach the -> 60x240mm
    result1 = conn.execute(
        text("""
            UPDATE products
            SET size = :size, size_en = :size_en, size_zh = :size_zh
            WHERE sku = :sku1 OR sku = :sku2
        """),
        {
            "size": GACH_THE_SIZE,
            "size_en": GACH_THE_SIZE_EN,
            "size_zh": GACH_THE_SIZE_ZH,
            "sku1": "OS.16",
            "sku2": "OS.17",
        },
    )
    print(f"[OK] Da cap nhat {result1.rowcount} san pham gach the -> 60x240mm")

    # 2. Cap nhat tat ca san pham con lai -> 600x1200mm
    result2 = conn.execute(
        text("""
            UPDATE products
            SET size = :size, size_en = :size_en, size_zh = :size_zh
            WHERE sku != :sku1 AND sku != :sku2
        """),
        {
            "size": DEFAULT_SIZE,
            "size_en": DEFAULT_SIZE_EN,
            "size_zh": DEFAULT_SIZE_ZH,
            "sku1": "OS.16",
            "sku2": "OS.17",
        },
    )
    print(f"[OK] Da cap nhat {result2.rowcount} san pham con lai -> 600x1200mm")

    # 3. Kiem tra ket qua
    rows = conn.execute(
        text("SELECT sku, name, size, size_en FROM products ORDER BY sku")
    ).fetchall()

    print("\n--- Ket qua sau khi cap nhat ---")
    print(f"{'SKU':<12} {'Ten':<25} {'Kich thuoc':<35} {'Size EN':<35}")
    print("-" * 107)
    for row in rows:
        print(f"{row[0] or 'N/A':<12} {row[1]:<25} {row[2] or 'N/A':<35} {row[3] or 'N/A':<35}")

print("\n[DONE] Hoan tat cap nhat kich thuoc san pham!")
