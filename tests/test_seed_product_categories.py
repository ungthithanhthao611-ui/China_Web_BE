from sqlalchemy import select

from app.db.init_db import seed_product_categories
from app.models.products import ProductCategory


def test_seed_product_categories_keeps_existing_admin_categories(db_session):
    db_session.add(
        ProductCategory(
            name="Custom Admin Category",
            slug="custom-admin-category",
            description="Created manually in admin",
            sort_order=30,
            is_active=True,
        )
    )
    db_session.commit()

    seed_product_categories(db_session)
    db_session.commit()

    target = db_session.scalar(
        select(ProductCategory).where(ProductCategory.slug == "da-mem-op-tuong-linh-hoat")
    )
    custom = db_session.scalar(
        select(ProductCategory).where(ProductCategory.slug == "custom-admin-category")
    )

    assert target is not None
    assert custom is not None
