import sys
sys.path.insert(0, '.')
from app.db.session import SessionLocal
from sqlalchemy import text
db = SessionLocal()
print(db.execute(text("SELECT * FROM project_products")).fetchall())
