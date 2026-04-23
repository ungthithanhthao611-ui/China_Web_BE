import psycopg
db_url = 'postgresql://postgres:123456@127.0.0.1:5432/china_web_db'
with psycopg.connect(db_url) as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT column_name, data_type, character_maximum_length FROM information_schema.columns WHERE table_name = 'products';")
        for row in cur.fetchall():
            print(row)
