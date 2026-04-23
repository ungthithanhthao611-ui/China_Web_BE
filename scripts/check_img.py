import psycopg
db_url = 'postgresql://postgres:123456@127.0.0.1:5432/china_web_db'
with psycopg.connect(db_url) as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT id, name, image_url FROM products LIMIT 5;")
        for row in cur.fetchall():
            print(row)
