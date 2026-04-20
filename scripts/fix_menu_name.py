import psycopg

db_url = "postgresql://postgres:123456@127.0.0.1:5432/china_web_db"

def fix():
    conn = psycopg.connect(db_url)
    cursor = conn.cursor()
    # Rename to match frontend pattern search
    cursor.execute("UPDATE menus SET name = 'Main Navigation' WHERE id = 1")
    conn.commit()
    cursor.close()
    conn.close()

if __name__ == "__main__":
    fix()
