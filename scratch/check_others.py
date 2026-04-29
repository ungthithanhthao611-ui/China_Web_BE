from sqlalchemy import create_engine, inspect
from app.core.config import settings

def main():
    engine = create_engine(settings.database_url)
    inspector = inspect(engine)
    
    tables = ["users", "admin_users", "carts"]
    for table in tables:
        if table in inspector.get_table_names():
            pk = inspector.get_pk_constraint(table)
            print(f"Table {table} PK: {pk}")
        else:
            print(f"Table {table} does not exist.")

if __name__ == "__main__":
    main()
