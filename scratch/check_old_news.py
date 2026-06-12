import os
import sys
from sqlalchemy import create_engine

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

def main():
    db_url = "postgresql+psycopg://neondb_owner:npg_JulyU3iATW9G@ep-calm-snow-a1iw65i0-pooler.ap-southeast-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
    print(f"Connecting to database: {db_url}")
    engine = create_engine(db_url)
    with engine.connect() as conn:
        from sqlalchemy import text
        res = conn.execute(text("SELECT id, title, slug, status FROM news_posts;")).all()
        print(f"Total records found: {len(res)}")
        for r in res:
            title_str = str(r[1]).encode('ascii', 'replace').decode('ascii')
            print(f"ID: {r[0]} | Title: {title_str} | Slug: {r[2]} | Status: {r[3]}")

if __name__ == "__main__":
    main()
