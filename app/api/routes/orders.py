from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin_user, get_db
from app.api.routes.user_auth import get_current_user
from app.models.user import User
from app.schemas.orders import (
  OrderAdminWriteRequest,
  OrderCreateRequest,
  OrderHistoryResponse,
  OrderRead,
)
from app.services.orders import create_order_from_cart, get_user_orders, update_order_admin

router = APIRouter()


@router.post('/', response_model=OrderRead)
def create_order(
  payload: OrderCreateRequest,
  db: Session = Depends(get_db),
  current_user: User = Depends(get_current_user),
) -> OrderRead:
  return create_order_from_cart(db=db, user=current_user, payload=payload)


@router.get('/', response_model=OrderHistoryResponse)
def list_my_orders(
  db: Session = Depends(get_db),
  current_user: User = Depends(get_current_user),
) -> OrderHistoryResponse:
  return get_user_orders(db=db, user=current_user)


@router.put('/admin/{order_id}', response_model=OrderRead)
def update_admin_order(
  order_id: int,
  payload: OrderAdminWriteRequest,
  db: Session = Depends(get_db),
  _: object = Depends(get_current_admin_user),
) -> OrderRead:
  return update_order_admin(db=db, order_id=order_id, payload=payload)
