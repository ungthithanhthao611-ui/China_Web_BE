from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.products import Product, ProductCategory

def seed_products(session: Session) -> None:
    # 1. Get Category
    category = session.scalar(select(ProductCategory).where(ProductCategory.slug == "da-mem-op-tuong-linh-hoat"))
    if not category:
        return

    # 2. Define Products
    products_data = [
        ("OS.01", "Travertine", 1290000, 0, 24),
        ("OS.01.3D", "Travertine 3D", 1490000, 1390000, 8),
        ("OS.02", "Vân vải", 990000, 0, 17),
        ("OS.03", "Đá phiến sét", 1190000, 0, 11),
        ("OS.03.3D", "Đá phiến 3D", 1390000, 1290000, 4),
        ("OS.04", "Vân đan sợi", 1090000, 0, 13),
        ("OS.05", "Đá tinh nguyệt", 1250000, 0, 7),
        ("OS.06", "Đá hoa cương", 1350000, 0, 9),
        ("OS.06.3D", "Đá hoa cương 3D", 1550000, 1450000, 3),
        ("OS.07", "Đá xẻ rãnh", 1150000, 0, 14),
        ("OS.08", "Đất nện", 980000, 0, 20),
        ("OS.09", "Đá dacit", 1280000, 0, 6),
        ("OS.10", "Đan tre", 1180000, 0, 10),
        ("OS.11", "Đá nước chảy", 1320000, 1250000, 5),
        ("OS.12", "Đá vân sóng", 1260000, 0, 12),
        ("OS.13", "Đá chẻ", 1210000, 0, 15),
        ("OS.14", "Đá vân sọc", 1240000, 0, 16),
        ("OS.15", "Đá vôi", 1160000, 0, 18),
        ("OS.16", "Gạch thẻ", 890000, 0, 22),
        ("OS.17", "Gạch thẻ cổ điển", 940000, 0, 19),
    ]

    # 3. Upsert by SKU: only create new products, never delete existing ones.
    #    This preserves product IDs, image_url, and product_images relationships.
    existing_by_sku = {
        p.sku: p for p in session.scalars(select(Product)).all() if p.sku
    }

    for idx, (sku, name, price, sale_price, stock_quantity) in enumerate(products_data):
        slug = f"da-mem-{sku.lower().replace('.', '-')}"
        sort_order = (idx + 1) * 10

        existing = existing_by_sku.get(sku)
        if existing:
            # Update only structural fields that won't overwrite user data.
            # Do NOT overwrite image_url, short_desc, full_desc, pricing, stock, etc.
            if not existing.category_id:
                existing.category_id = category.id
            if not existing.slug:
                existing.slug = slug
            session.add(existing)
            continue

        product = Product(
            category_id=category.id,
            sku=sku,
            name=name,
            slug=slug,
            short_desc=f"{name} là dòng đá mềm ốp tường linh hoạt cao cấp của Thiên Đông Việt Nam.",
            full_desc="Sản phẩm được làm từ bột đá thiên nhiên kết hợp với polymer cao cấp, mang đến sự linh hoạt, bền bỉ và thẩm mỹ cao cho mọi công trình.",
            size="600x1200mm (Kích thước mẫu)",
            material="Bột đá tự nhiên & Polymer",
            price=price,
            original_price=price,
            sale_price=sale_price,
            stock_quantity=stock_quantity,
            is_active=True,
            sort_order=sort_order,
        )
        session.add(product)

    session.flush()
