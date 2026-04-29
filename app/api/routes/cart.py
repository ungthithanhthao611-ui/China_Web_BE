from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.routes.user_auth import get_current_user
from app.models.user import User
from app.schemas.cart import CartRead, CartItemCreate, CartItemUpdate
from app.services.cart import (
    get_or_create_cart,
    add_item_to_cart,
    update_cart_item,
    remove_from_cart,
    clear_cart
)

router = APIRouter()


@router.get("/", response_model=CartRead)
def get_cart(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> CartRead:
    return get_or_create_cart(db, current_user.id)


@router.post("/items", response_model=CartRead)
def add_to_cart(
    payload: CartItemCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> CartRead:
    return add_item_to_cart(db, current_user.id, payload)


@router.patch("/items/{item_id}", response_model=CartRead)
def update_item(
    item_id: int,
    payload: CartItemUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> CartRead:
    return update_cart_item(db, current_user.id, item_id, payload)


@router.delete("/items/{item_id}", response_model=CartRead)
def remove_item(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> CartRead:
    return remove_from_cart(db, current_user.id, item_id)


@router.delete("/", response_model=CartRead)
def empty_cart(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> CartRead:
    return clear_cart(db, current_user.id)
