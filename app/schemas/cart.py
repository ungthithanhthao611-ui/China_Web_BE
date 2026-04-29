from pydantic import BaseModel
from app.schemas.user import UserRead
from app.schemas.products import ProductImageRead


class CartItemBase(BaseModel):
    product_id: int
    quantity: int = 1


class CartItemCreate(CartItemBase):
    pass


class CartItemUpdate(BaseModel):
    quantity: int


class ProductShort(BaseModel):
    id: int
    sku: str | None = None
    name: str
    slug: str
    image_url: str | None = None
    price: float | None = 0.0
    images: list[ProductImageRead] = []

    class Config:
        from_attributes = True


class CartItemRead(CartItemBase):
    id: int
    product: ProductShort

    class Config:
        from_attributes = True


class CartRead(BaseModel):
    id: int
    user_id: int
    items: list[CartItemRead] = []

    class Config:
        from_attributes = True
