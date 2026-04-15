from app.db.session import engine
from sqlalchemy import text

with engine.connect() as conn:
    conn.execute(text('ALTER TABLE contacts ADD COLUMN IF NOT EXISTS postal_code VARCHAR(20)'))
    conn.commit()
    print("Column added.")
    
with engine.connect() as conn:
    conn.execute(text("UPDATE contacts SET postal_code='100005' WHERE is_primary=true AND postal_code IS NULL"))
    conn.commit()
    print("Data updated.")
