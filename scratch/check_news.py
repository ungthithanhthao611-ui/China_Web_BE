import os
import sys
from sqlalchemy import create_engine, select

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

from app.core.config import settings
from app.models.news import NewsPost

def main():
    db_url = settings.database_url
    print(f"Connecting to database: {db_url}")
    engine = create_engine(db_url)
    with engine.connect() as conn:
        # Select all records from news_posts
        from sqlalchemy import text
        res = conn.execute(text("SELECT id, title, slug, status, deleted_at FROM news_posts;")).all()
        print(f"Total records found: {len(res)}")
        for r in res:
            title_str = str(r[1]).encode('ascii', 'replace').decode('ascii')
            print(f"ID: {r[0]} | Title: {title_str} | Slug: {r[2]} | Status: {r[3]} | Deleted At: {r[4]}")

if __name__ == "__main__":
    main()
