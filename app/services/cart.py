from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from fastapi import HTTPException, status

from app.models.products import Cart, CartItem, Product
from app.schemas.cart import CartItemCreate, CartItemUpdate


def get_or_create_cart(db: Session, user_id: int) -> Cart:
    cart = db.scalar(
        select(Cart)
        .where(Cart.user_id == user_id)
        .options(selectinload(Cart.items).selectinload(CartItem.product).selectinload(Product.images))
    )
    if not cart:
        cart = Cart(user_id=user_id)
        db.add(cart)
        db.commit()
        db.refresh(cart)
    return cart


def add_item_to_cart(db: Session, user_id: int, payload: CartItemCreate) -> Cart:
    cart = get_or_create_cart(db, user_id)

    # Check if product exists
    product = db.get(Product, payload.product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    stock_quantity = max(0, int(getattr(product, "stock_quantity", 0) or 0))
    if stock_quantity <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Sản phẩm hiện đã hết hàng")

    requested_quantity = max(1, int(payload.quantity or 1))

    # Check if item already in cart
    item = db.scalar(
        select(CartItem).where(
            CartItem.cart_id == cart.id,
            CartItem.product_id == payload.product_id
        )
    )

    next_quantity = requested_quantity
    if item:
        next_quantity = int(item.quantity or 0) + requested_quantity

    if next_quantity > stock_quantity:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Chỉ còn {stock_quantity} sản phẩm trong kho"
        )

    if item:
        item.quantity = next_quantity
    else:
        item = CartItem(
            cart_id=cart.id,
            product_id=payload.product_id,
            quantity=requested_quantity
        )
        db.add(item)

    db.commit()
    db.refresh(cart)
    return cart


def update_cart_item(db: Session, user_id: int, item_id: int, payload: CartItemUpdate) -> Cart:
    cart = get_or_create_cart(db, user_id)
    item = db.get(CartItem, item_id)
    
    if not item or item.cart_id != cart.id:
        raise HTTPException(status_code=404, detail="Cart item not found")
    
    if payload.quantity <= 0:
        db.delete(item)
    else:
        product = db.get(Product, item.product_id)
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")

        stock_quantity = max(0, int(getattr(product, "stock_quantity", 0) or 0))
        if stock_quantity <= 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Sản phẩm hiện đã hết hàng")

        next_quantity = max(1, int(payload.quantity or 1))
        if next_quantity > stock_quantity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Chỉ còn {stock_quantity} sản phẩm trong kho"
            )

        item.quantity = next_quantity
    
    db.commit()
    db.refresh(cart)
    return cart


def remove_from_cart(db: Session, user_id: int, item_id: int) -> Cart:
    cart = get_or_create_cart(db, user_id)
    item = db.get(CartItem, item_id)
    
    if not item or item.cart_id != cart.id:
        raise HTTPException(status_code=404, detail="Cart item not found")
    
    db.delete(item)
    db.commit()
    db.refresh(cart)
    return cart


def clear_cart(db: Session, user_id: int) -> Cart:
    cart = get_or_create_cart(db, user_id)
    for item in cart.items:
        db.delete(item)
    db.commit()
    db.refresh(cart)
    return cart
