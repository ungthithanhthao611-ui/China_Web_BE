import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import SessionLocal
from app.db.session import SessionLocal
from sqlalchemy import text

def main():
    db = SessionLocal()
    try:
        # Delete related entity_media where entity_type is 'project'
        db.execute(text("DELETE FROM entity_media WHERE entity_type = 'project';"))
        
        # Delete project relationships
        db.execute(text("DELETE FROM project_products;"))
        db.execute(text("DELETE FROM project_category_items;"))

        # Delete projects
        db.execute(text("DELETE FROM projects;"))

        db.commit()
        print("Success! All previous project data has been wiped.")
    except Exception as e:
        db.rollback()
        print(f"Error during deletion: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    main()
