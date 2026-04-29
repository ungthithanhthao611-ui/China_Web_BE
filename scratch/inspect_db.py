from sqlalchemy import create_engine, inspect
from app.core.config import settings

def main():
    engine = create_engine(settings.database_url)
    inspector = inspect(engine)
    
    if "products" not in inspector.get_table_names():
        print("Table 'products' does not exist.")
        return

    print(f"Inspecting table: products")
    columns = inspector.get_columns("products")
    for col in columns:
        print(f"  Column: {col['name']}, Details: {col}")
    
    pk = inspector.get_pk_constraint("products")
    print(f"Primary Key Constraint: {pk}")
    
    unique_constraints = inspector.get_unique_constraints("products")
    print(f"Unique Constraints: {unique_constraints}")

if __name__ == "__main__":
    main()
