import logging
from sqlalchemy import select
from app.core.config import settings
from app.core.security import hash_password
from app.db.session import engine, SessionLocal
from app.models.base import Base
from app.models.admin import AdminUser
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
    
    with SessionLocal() as session:
        try:
            # 1. Seed Languages
            seed_languages(session)
            
            # 2. Seed Initial Admin User
            seed_admin_user(session)
            
            session.commit()
            logger.info("Database initialization completed successfully.")
        except Exception as e:
            session.rollback()
            logger.error("Error during database initialization: %s", e)
            # We don't raise here to allow the app to start even if seeding fails
            # but tables should be created by metadata.create_all above.

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
