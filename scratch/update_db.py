import sqlite3
import os

db_path = './china_web.db'
if not os.path.exists(db_path):
    print(f"Database file not found at {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

try:
    cursor.execute("PRAGMA table_info(contact_inquiries)")
    columns = [row[1] for row in cursor.fetchall()]
    
    if 'admin_response' not in columns:
        print("Adding admin_response column to contact_inquiries table...")
        cursor.execute("ALTER TABLE contact_inquiries ADD COLUMN admin_response TEXT")
        conn.commit()
        print("Column added successfully.")
    else:
        print("admin_response column already exists.")

except Exception as e:
    print(f"Error: {e}")
finally:
    conn.close()
