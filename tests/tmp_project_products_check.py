import sys
sys.path.insert(0, '.')

from sqlalchemy import text
from app.db.session import SessionLocal
from app.services.admin import create_entity_record

db = SessionLocal()

projects = db.execute(text("SELECT id, title, slug FROM projects ORDER BY id DESC LIMIT 5")).fetchall()
products = db.execute(text("SELECT id, name, slug, is_active FROM products ORDER BY id DESC LIMIT 10")).fetchall()
print('PROJECTS:', projects)
print('PRODUCTS:', products)

if projects and products:
    payload = {
        'project_id': int(projects[0][0]),
        'product_id': int(products[0][0]),
        'sort_order': 10,
        'note': 'test mapping',
    }
    try:
        result = create_entity_record(db=db, entity_name='project_products', payload=payload)
        print('CREATED:', result)
    except Exception as exc:
        print('CREATE_ERROR:', repr(exc))

rows = db.execute(text("SELECT id, project_id, product_id, sort_order, note FROM project_products ORDER BY id DESC LIMIT 10")).fetchall()
print('PROJECT_PRODUCTS:', rows)
