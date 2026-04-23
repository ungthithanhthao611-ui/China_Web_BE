import psycopg
db_url = 'postgresql://postgres:123456@127.0.0.1:5432/china_web_db'
with psycopg.connect(db_url) as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT product_id, url FROM product_images LIMIT 5;")
        print('product_images:', cur.fetchall())
        cur.execute("SELECT entity_id, media_id FROM entity_media WHERE entity_type='product' LIMIT 5;")
        print('entity_media:', cur.fetchall())
