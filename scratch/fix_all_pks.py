from sqlalchemy import create_engine, inspect, text
from app.core.config import settings

def main():
    engine = create_engine(settings.database_url)
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    
    with engine.connect() as conn:
        for table in tables:
            pk = inspector.get_pk_constraint(table)
            if not pk or not pk.get("constrained_columns"):
                print(f"Table {table} is missing a Primary Key. Adding one on 'id'...")
                try:
                    # Assume 'id' is the PK column
                    conn.execute(text(f"ALTER TABLE {table} ADD CONSTRAINT pk_{table} PRIMARY KEY (id)"))
                    conn.commit()
                    print(f"  Successfully added PK to {table}.")
                except Exception as e:
                    print(f"  Failed to add PK to {table}: {e}")
            else:
                print(f"Table {table} already has a PK: {pk.get('constrained_columns')}")

if __name__ == "__main__":
    main()
