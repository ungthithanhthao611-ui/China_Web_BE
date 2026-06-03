import os
import sys
from sqlalchemy import create_engine, inspect
# Add parent directory to sys.path to be able to import app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings

def main():
    engine = create_engine(settings.database_url)
    inspector = inspect(engine)
    columns = inspector.get_columns("site_settings")
    for col in columns:
        print(f"Column: {col['name']}, Type: {col['type']}")

if __name__ == "__main__":
    main()
