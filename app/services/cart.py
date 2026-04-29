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

    # Check if item already in cart
    item = db.scalar(
        select(CartItem).where(
            CartItem.cart_id == cart.id, 
            CartItem.product_id == payload.product_id
        )
    )
    
    if item:
        item.quantity += payload.quantity
    else:
        item = CartItem(
            cart_id=cart.id,
            product_id=payload.product_id,
            quantity=payload.quantity
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
        item.quantity = payload.quantity
    
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
