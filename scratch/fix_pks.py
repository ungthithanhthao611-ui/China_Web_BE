from sqlalchemy import create_engine, text
from app.core.config import settings

def main():
    engine = create_engine(settings.database_url)
    with engine.connect() as conn:
        print("Adding primary key to products table...")
        try:
            conn.execute(text("ALTER TABLE products ADD CONSTRAINT pk_products PRIMARY KEY (id)"))
            conn.commit()
            print("Successfully added primary key to products.")
        except Exception as e:
            print(f"Failed to add primary key to products: {e}")

        print("Adding primary key to product_categories table...")
        try:
            conn.execute(text("ALTER TABLE product_categories ADD CONSTRAINT pk_product_categories PRIMARY KEY (id)"))
            conn.commit()
            print("Successfully added primary key to product_categories.")
        except Exception as e:
            print(f"Failed to add primary key to product_categories: {e}")

if __name__ == "__main__":
    main()
