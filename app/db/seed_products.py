from sqlalchemy import select, delete
from sqlalchemy.orm import Session
from app.models.products import Product, ProductCategory

def seed_products(session: Session) -> None:
    # 1. Get Category
    category = session.scalar(select(ProductCategory).where(ProductCategory.slug == "da-mem-op-tuong-linh-hoat"))
    if not category:
        return

    # 2. Define Products
    products_data = [
        ("OS.01", "Travertine"),
        ("OS.01.3D", "Travertine 3D"),
        ("OS.02", "Vân vải"),
        ("OS.03", "Đá phiến sét"),
        ("OS.03.3D", "Đá phiến 3D"),
        ("OS.04", "Vân đan sợi"),
        ("OS.05", "Đá tinh nguyệt"),
        ("OS.06", "Đá hoa cương"),
        ("OS.06.3D", "Đá hoa cương 3D"),
        ("OS.07", "Đá xẻ rãnh"),
        ("OS.08", "Đất nện"),
        ("OS.09", "Đá dacit"),
        ("OS.10", "Đan tre"),
        ("OS.11", "Đá nước chảy"),
        ("OS.12", "Đá vân sóng"),
        ("OS.13", "Đá chẻ"),
        ("OS.14", "Đá vân sọc"),
        ("OS.15", "Đá vôi"),
        ("OS.16", "Gạch thẻ"),
        ("OS.17", "Gạch thẻ cổ điển"),
    ]

    # 3. Clear existing products (as requested: "cái nào k đúng dl thì xóa")
    session.execute(delete(Product))
    session.flush()

    # 4. Add new products
    for idx, (sku, name) in enumerate(products_data):
        slug = f"da-mem-{sku.lower().replace('.', '-')}"
        product = Product(
            category_id=category.id,
            sku=sku,
            name=name,
            slug=slug,
            short_desc=f"{name} là dòng đá mềm ốp tường linh hoạt cao cấp của Thiên Đông Việt Nam.",
            full_desc="Sản phẩm được làm từ bột đá thiên nhiên kết hợp với polymer cao cấp, mang đến sự linh hoạt, bền bỉ và thẩm mỹ cao cho mọi công trình.",
            size="600x1200mm (Kích thước mẫu)",
            material="Bột đá tự nhiên & Polymer",
            is_active=True,
            sort_order=(idx + 1) * 10
        )
        session.add(product)
    
    session.flush()
