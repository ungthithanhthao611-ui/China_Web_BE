import psycopg
db_url = 'postgresql://postgres:123456@127.0.0.1:5432/china_web_db'
with psycopg.connect(db_url) as conn:
    with conn.cursor() as cur:
        cur.execute("ALTER TABLE products ALTER COLUMN color TYPE TEXT;")
    conn.commit()
print('Altered color column to TEXT successfully.')
