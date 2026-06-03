import os
import sys
from sqlalchemy import create_engine, text
# Add parent directory to sys.path to be able to import app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings

def main():
    sys.stdout.reconfigure(encoding='utf-8')
    engine = create_engine(settings.database_url)
    with engine.connect() as conn:
        result = conn.execute(text("SELECT id, config_key, language_id, config_value FROM site_settings WHERE config_key = 'production_capabilities_json'"))
        for row in result:
            print(f"ID: {row[0]}, Key: {row[1]}, Language ID: {row[2]}")
            print(f"Value: {row[3]}")
            print("-" * 40)

if __name__ == "__main__":
    main()
