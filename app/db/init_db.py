import logging
from sqlalchemy import inspect, text
from sqlalchemy import select
from app.core.config import settings
from app.core.security import hash_password
from app.db.session import engine, SessionLocal
from app.models.base import Base
from app.models.admin import AdminUser
from app.models.products import ProductCategory
from app.models.taxonomy import Language
# Import all models to ensure they are registered
from app.db import base as _  # noqa: F401

logger = logging.getLogger(__name__)

def initialize_database() -> None:
    """
    Initialize the database: create tables and seed initial data.
    This function is called on application startup (lifespan).
    """
    logger.info("Initializing database...")
    # Create tables
    Base.metadata.create_all(bind=engine)
    ensure_admin_user_schema()
    
    with SessionLocal() as session:
        try:
            # 1. Seed Languages
            seed_languages(session)
            
            # 2. Seed Initial Admin User
            seed_admin_user(session)

            # 3. Seed baseline product categories required by legacy flows/tests
            seed_product_categories(session)
            
            session.commit()
            logger.info("Database initialization completed successfully.")
        except Exception as e:
            session.rollback()
            logger.error("Error during database initialization: %s", e)
            # We don't raise here to allow the app to start even if seeding fails
            # but tables should be created by metadata.create_all above.


def ensure_admin_user_schema() -> None:
    inspector = inspect(engine)
    if "admin_users" not in inspector.get_table_names():
        return

    existing_columns = {column["name"] for column in inspector.get_columns("admin_users")}
    statements: list[str] = []

    if "email" not in existing_columns:
        statements.append("ALTER TABLE admin_users ADD COLUMN email VARCHAR(255)")
    if "phone" not in existing_columns:
        statements.append("ALTER TABLE admin_users ADD COLUMN phone VARCHAR(32)")
    if "avatar_url" not in existing_columns:
        statements.append("ALTER TABLE admin_users ADD COLUMN avatar_url VARCHAR(1000)")

    if not statements:
        return

    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))

def seed_languages(session) -> None:
    languages_data = [
        {"code": "vi", "name": "Vietnamese", "is_default": True},
        {"code": "en", "name": "English", "is_default": False},
        {"code": "zh", "name": "Chinese", "is_default": False},
    ]
    
    for lang_data in languages_data:
        lang = session.scalar(select(Language).where(Language.code == lang_data["code"]))
        if not lang:
            logger.info("Adding language: %s", lang_data["code"])
            lang = Language(**lang_data)
            session.add(lang)

def seed_admin_user(session) -> None:
    admin_user = session.scalar(
        select(AdminUser).where(AdminUser.username == settings.initial_admin_username)
    )
    
    if not admin_user:
        logger.info("Creating initial admin user: %s", settings.initial_admin_username)
        admin_user = AdminUser(
            username=settings.initial_admin_username,
            password_hash=hash_password(settings.initial_admin_password),
            role="admin",
            is_active=True,
        )
        session.add(admin_user)
    else:
        logger.info("Admin user already exists.")


def seed_product_categories(session) -> None:
    baseline_categories = [
        {
            "name": "Đá mềm ốp tường linh hoạt",
            "name_en": "Flexible Stone Wall Cladding",
            "name_zh": "柔性石材墙面饰材",
            "slug": "da-mem-op-tuong-linh-hoat",
            "description": "Danh mục sản phẩm đá mềm ốp tường linh hoạt.",
            "description_en": "Flexible stone wall cladding product category.",
            "description_zh": "柔性石材墙面饰材 product category.",
            "sort_order": 10,
            "is_active": True,
        }
    ]

    for payload in baseline_categories:
        category = session.scalar(select(ProductCategory).where(ProductCategory.slug == payload["slug"]))
        if category:
            continue

        logger.info("Adding product category: %s", payload["slug"])
        session.add(ProductCategory(**payload))
