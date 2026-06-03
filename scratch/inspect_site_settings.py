import os
import sys
from sqlalchemy import create_engine, text
# Add parent directory to sys.path to be able to import app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings

def main():
    # Force UTF-8 for output
    sys.stdout.reconfigure(encoding='utf-8')
    engine = create_engine(settings.database_url)
    with engine.connect() as conn:
        result = conn.execute(text("SELECT config_key, config_value FROM site_settings WHERE config_key LIKE '%capability%' OR config_key LIKE '%factory%' OR config_key LIKE '%production%'"))
        for row in result:
            print(f"Key: {row[0]}")
            print(f"Value: {row[1]}")
            print("-" * 40)

if __name__ == "__main__":
    main()
