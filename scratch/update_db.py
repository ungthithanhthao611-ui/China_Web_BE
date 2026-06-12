import os
import sys
from sqlalchemy import create_engine, text

# Add the project root to sys.path so we can import app modules
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

from app.core.config import settings

def main():
    db_url = settings.database_url
    print(f"Connecting to database: {db_url}")
    
    # Create engine and execute the ALTER TABLE SQL command
    engine = create_engine(db_url)
    with engine.connect() as conn:
        print("Modifying news_posts.thumbnail_url column type to TEXT...")
        conn.execute(text("ALTER TABLE news_posts ALTER COLUMN thumbnail_url TYPE TEXT;"))
        conn.commit()
        print("ALTER TABLE query executed successfully!")

if __name__ == "__main__":
    try:
        main()
        print("Migration done.")
    except Exception as e:
        print(f"Migration failed: {e}")
        sys.exit(1)
