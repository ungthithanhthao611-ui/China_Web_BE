import argparse
import sys
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
# Import tất cả models để tránh lỗi "class not found" khi khởi tạo mapper
from app.models.products import Product, ProductCategory
from app.models.projects import Project, ProjectProduct
from app.models.media import MediaAsset, EntityMedia

def fix_orphan_project_products(*, apply: bool = False) -> None:
    db: Session = SessionLocal()
    try:
        # 1. Lấy tất cả mappings sản phẩm trong dự án
        all_pp = db.scalars(select(ProjectProduct)).all()
        
        # 2. Lấy danh sách ID sản phẩm đang thực sự tồn tại
        existing_product_ids = set(db.scalars(select(Product.id)).all())

        # 3. Lọc ra các bản ghi mồ côi (trỏ tới ID không tồn tại)
        orphans = [pp for pp in all_pp if pp.product_id not in existing_product_ids]

        if not orphans:
            print("✅ Không tìm thấy sản phẩm mồ côi nào trong dự án. Dữ liệu Mapping đang sạch!")
            return

        print(f"⚠️  Phát hiện {len(orphans)} liên kết sản phẩm bị lỗi ID (không tồn tại trong danh mục):")
        for pp in orphans:
            print(f"   - Mapping ID: {pp.id} | Dự án ID: {pp.project_id} | Sản phẩm ID lỗi: {pp.product_id}")

        if not apply:
            print(f"\n👉 Đây là chế độ kiểm tra (Dry-run). Chạy với --apply để thực hiện xóa.")
            return

        print(f"\n🚀 Đang xóa {len(orphans)} liên kết lỗi...")
        for pp in orphans:
            db.delete(pp)
        
        db.commit()
        print(f"✅ Đã dọn dẹp xong. Bây giờ bạn có thể vào Admin chọn lại sản phẩm mới cho dự án.")

    except Exception as e:
        db.rollback()
        print(f"❌ Lỗi: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Thực thi lệnh xóa")
    args = parser.parse_args()
    fix_orphan_project_products(apply=args.apply)
