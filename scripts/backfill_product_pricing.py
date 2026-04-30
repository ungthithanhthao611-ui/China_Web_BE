from pathlib import Path
import sys

from sqlalchemy import select

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import app.models.content  # noqa: F401
import app.models.media  # noqa: F401
import app.models.organization  # noqa: F401
import app.models.orders  # noqa: F401
import app.models.products  # noqa: F401
import app.models.projects  # noqa: F401
import app.models.taxonomy  # noqa: F401
import app.models.user  # noqa: F401
from app.db.session import SessionLocal
from app.models.products import Product

DEFAULTS = {
    'OS.01': {'price': 1290000, 'sale_price': 0, 'stock_quantity': 24},
    'OS.01.3D': {'price': 1490000, 'sale_price': 1390000, 'stock_quantity': 8},
    'OS.02': {'price': 990000, 'sale_price': 0, 'stock_quantity': 17},
    'OS.03': {'price': 1190000, 'sale_price': 0, 'stock_quantity': 11},
    'OS.03.3D': {'price': 1390000, 'sale_price': 1290000, 'stock_quantity': 4},
    'OS.04': {'price': 1090000, 'sale_price': 0, 'stock_quantity': 13},
    'OS.05': {'price': 1250000, 'sale_price': 0, 'stock_quantity': 7},
    'OS.06': {'price': 1350000, 'sale_price': 0, 'stock_quantity': 9},
    'OS.06.3D': {'price': 1550000, 'sale_price': 1450000, 'stock_quantity': 3},
    'OS.07': {'price': 1150000, 'sale_price': 0, 'stock_quantity': 14},
    'OS.08': {'price': 980000, 'sale_price': 0, 'stock_quantity': 20},
    'OS.09': {'price': 1280000, 'sale_price': 0, 'stock_quantity': 6},
    'OS.10': {'price': 1180000, 'sale_price': 0, 'stock_quantity': 10},
    'OS.11': {'price': 1320000, 'sale_price': 1250000, 'stock_quantity': 5},
    'OS.12': {'price': 1260000, 'sale_price': 0, 'stock_quantity': 12},
    'OS.13': {'price': 1210000, 'sale_price': 0, 'stock_quantity': 15},
    'OS.14': {'price': 1240000, 'sale_price': 0, 'stock_quantity': 16},
    'OS.15': {'price': 1160000, 'sale_price': 0, 'stock_quantity': 18},
    'OS.16': {'price': 890000, 'sale_price': 0, 'stock_quantity': 22},
    'OS.17': {'price': 940000, 'sale_price': 0, 'stock_quantity': 19},
}


def main() -> None:
    session = SessionLocal()
    try:
        products = session.scalars(select(Product).where(Product.sku.in_(DEFAULTS.keys()))).all()
        updated = 0
        for product in products:
            defaults = DEFAULTS.get(product.sku)
            if not defaults:
                continue
            product.price = defaults['price']
            product.original_price = defaults['price']
            product.sale_price = defaults['sale_price']
            product.stock_quantity = defaults['stock_quantity']
            session.add(product)
            updated += 1
        session.commit()
        print({'updated': updated})
    finally:
        session.close()


if __name__ == '__main__':
    main()
