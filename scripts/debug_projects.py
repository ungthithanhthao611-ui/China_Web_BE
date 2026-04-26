from sqlalchemy import select
from app.db.session import SessionLocal
from app.db.base import *  # This imports all models and avoids mapper issues

def debug_project_data():
    db = SessionLocal()
    try:
        # Lấy toàn bộ projects
        projects = db.scalars(select(Project)).all()
        if not projects:
            print("❌ Không có dự án nào trong DB.")
            return

        for p in projects:
            print(f"\n--- Project: {p.title} (ID: {p.id}) ---")
            
            # Check products
            pps = db.scalars(select(ProjectProduct).where(ProjectProduct.project_id == p.id)).all()
            print(f"Products Mapping ({len(pps)}):")
            for pp in pps:
                prod = db.get(Product, pp.product_id)
                print(f"  - ProductID: {pp.product_id} | Name: {prod.name if prod else 'MISSING'}")

            # Check gallery
            ems = db.scalars(select(EntityMedia).where(
                EntityMedia.entity_id == p.id, 
                EntityMedia.entity_type == 'project'
            )).all()
            print(f"Gallery Images ({len(ems)}):")
            for em in ems:
                media = db.get(MediaAsset, em.media_id)
                print(f"  - MediaID: {em.media_id} | Group: {em.group_name} | URL: {media.url if media else 'MISSING'}")
                if media and not media.url:
                    print(f"    ⚠️ CẢNH BÁO: Media Asset {em.media_id} không có URL!")
    finally:
        db.close()

if __name__ == "__main__":
    debug_project_data()
