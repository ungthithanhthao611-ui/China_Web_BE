from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.models.orders import Order, OrderItem
from app.models.products import Cart, CartItem, Product
from app.models.user import User
from app.schemas.orders import (
  OrderAdminWriteRequest,
  OrderCreateRequest,
  OrderHistoryResponse,
  OrderRead,
)
from app.services.product_pricing import resolve_order_item_price_snapshot
from app.services.vnpay import normalize_vnpay_txn_ref

logger = logging.getLogger(__name__)

ALLOWED_PAYMENT_METHODS = {'cod', 'bank_transfer', 'vnpay'}
ORDER_STATUS_OPTIONS = (
  'pending_confirmation',
  'confirmed',
  'processing',
  'shipping',
  'delivered',
  'cancelled',
)
PAYMENT_STATUS_OPTIONS = ('unpaid', 'pending', 'paid', 'failed', 'refunded')
ORDER_STATUS_LABELS = {
  'pending_confirmation': 'Chờ xác nhận',
  'confirmed': 'Đã xác nhận',
  'processing': 'Đang chuẩn bị hàng',
  'shipping': 'Đang giao hàng',
  'delivered': 'Đã giao hàng',
  'cancelled': 'Đã hủy',
}
PAYMENT_STATUS_LABELS = {
  'unpaid': 'Chưa thanh toán',
  'pending': 'Đang chờ thanh toán',
  'paid': 'Đã thanh toán',
  'failed': 'Thanh toán thất bại',
  'refunded': 'Đã hoàn tiền',
}
PAYMENT_METHOD_LABELS = {
  'cod': 'Thanh toán khi nhận hàng',
  'bank_transfer': 'Chuyển khoản ngân hàng',
  'vnpay': 'Thanh toán qua VNPAY',
}
ALLOWED_ORDER_STATUS_TRANSITIONS = {
  'pending_confirmation': {'confirmed', 'cancelled'},
  'confirmed': {'processing', 'cancelled'},
  'processing': {'shipping', 'cancelled'},
  'shipping': {'delivered', 'cancelled'},
  'delivered': set(),
  'cancelled': set(),
}


def _normalize_price(value: float | int | None) -> float:
  if value is None:
    return 0.0
  try:
    return round(float(value), 2)
  except (TypeError, ValueError):
    return 0.0


def _normalize_text(value: str | None) -> str:
  return str(value or '').strip()


def _status_label(status_value: str | None) -> str:
  normalized = _normalize_text(status_value).lower()
  return ORDER_STATUS_LABELS.get(normalized, normalized or '-')


def _payment_status_label(status_value: str | None) -> str:
  normalized = _normalize_text(status_value).lower()
  return PAYMENT_STATUS_LABELS.get(normalized, normalized or '-')


def _payment_method_label(method_value: str | None) -> str:
  normalized = _normalize_text(method_value).lower()
  return PAYMENT_METHOD_LABELS.get(normalized, normalized or '-')


def _serialize_order(order: Order) -> OrderRead:
  payload = OrderRead.model_validate(order, from_attributes=True).model_dump()
  payload['status_label'] = _status_label(order.status)
  payload['payment_method_label'] = _payment_method_label(order.payment_method)
  payload['payment_status_label'] = _payment_status_label(order.payment_status)
  payload['item_count'] = sum(int(item.quantity or 0) for item in (order.items or []))
  return OrderRead.model_validate(payload)


def _generate_order_code(user_id: int) -> str:
  timestamp = datetime.now(timezone(timedelta(hours=7))).strftime('%Y%m%d%H%M%S')
  return normalize_vnpay_txn_ref(f'ORD{user_id}{timestamp}') or f'ORD{user_id}{timestamp}'


def _get_cart_with_items(db: Session, user_id: int) -> Cart | None:
  return db.scalar(
    select(Cart)
    .where(Cart.user_id == user_id)
    .options(selectinload(Cart.items).selectinload(CartItem.product).selectinload(Product.images)),
  )


def _get_order_with_items(db: Session, order_id: int) -> Order | None:
  return db.scalar(
    select(Order)
    .where(Order.id == order_id)
    .options(selectinload(Order.items)),
  )


def _get_existing_order_by_request_id(db: Session, client_request_id: str) -> Order | None:
  return db.scalar(
    select(Order)
    .where(Order.client_request_id == client_request_id)
    .options(selectinload(Order.items)),
  )


def get_user_order_by_id(db: Session, user_id: int, order_id: int) -> Order | None:
  return db.scalar(
    select(Order)
    .where(Order.id == order_id, Order.user_id == user_id)
    .options(selectinload(Order.items)),
  )


def get_order_by_code(db: Session, code: str) -> Order | None:
  normalized_code = normalize_vnpay_txn_ref(code)
  if not normalized_code:
    return None

  return db.scalar(
    select(Order)
    .where(Order.code == normalized_code)
    .options(selectinload(Order.items)),
  )


def _get_locked_products_by_ids(db: Session, product_ids: list[int]) -> dict[int, Product]:
  if not product_ids:
    return {}

  locked_products = db.scalars(
    select(Product)
    .where(Product.id.in_(product_ids))
    .with_for_update(),
  ).all()
  return {product.id: product for product in locked_products}


def _clear_user_cart_items(db: Session, user_id: int) -> None:
  cart = _get_cart_with_items(db, user_id)
  if not cart:
    return

  for item in list(cart.items or []):
    db.delete(item)


def _validate_order_status_transition(current_status: str, next_status: str) -> None:
  if current_status == next_status:
    return

  allowed_next_states = ALLOWED_ORDER_STATUS_TRANSITIONS.get(current_status, set())
  if next_status not in allowed_next_states:
    raise HTTPException(
      status_code=status.HTTP_409_CONFLICT,
      detail=(
        f'Không thể chuyển trạng thái đơn từ "{_status_label(current_status)}" '
        f'sang "{_status_label(next_status)}".'
      ),
    )


def _validate_payment_status(next_payment_status: str) -> None:
  if next_payment_status not in PAYMENT_STATUS_OPTIONS:
    raise HTTPException(
      status_code=status.HTTP_400_BAD_REQUEST,
      detail='Trạng thái thanh toán không hợp lệ.',
    )


def create_order_from_cart(db: Session, user: User, payload: OrderCreateRequest) -> OrderRead:
  payment_method = _normalize_text(payload.payment_method).lower() or 'cod'
  if payment_method not in ALLOWED_PAYMENT_METHODS:
    raise HTTPException(
      status_code=status.HTTP_400_BAD_REQUEST,
      detail='Phương thức thanh toán không được hỗ trợ.',
    )

  client_request_id = _normalize_text(payload.client_request_id)
  if not client_request_id:
    raise HTTPException(
      status_code=status.HTTP_400_BAD_REQUEST,
      detail='Thiếu mã yêu cầu thanh toán.',
    )

  existing_order = _get_existing_order_by_request_id(db, client_request_id)
  if existing_order:
    if existing_order.user_id != user.id:
      raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail='Mã yêu cầu thanh toán đã được sử dụng.',
      )
    return _serialize_order(existing_order)

  customer_name = _normalize_text(payload.customer_name)
  customer_phone = _normalize_text(payload.customer_phone)
  customer_email = _normalize_text(payload.customer_email).lower()
  shipping_address = _normalize_text(payload.shipping_address)
  note = _normalize_text(payload.note) or None

  try:
    cart = db.scalar(
      select(Cart)
      .where(Cart.user_id == user.id)
      .options(selectinload(Cart.items).selectinload(CartItem.product)),
    )
    cart_items = list(cart.items or []) if cart else []
    if not cart_items:
      raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail='Giỏ hàng đang trống. Không thể tạo đơn hàng.',
      )

    product_ids = sorted({item.product_id for item in cart_items if item.product_id})
    product_by_id = _get_locked_products_by_ids(db, product_ids)

    subtotal_amount = 0.0
    has_valid_items = False
    initial_payment_status = 'pending' if payment_method == 'vnpay' else 'unpaid'
    order = Order(
      user_id=user.id,
      code=_generate_order_code(user.id),
      client_request_id=client_request_id,
      status='pending_confirmation',
      payment_method=payment_method,
      payment_status=initial_payment_status,
      customer_name=customer_name,
      customer_phone=customer_phone,
      customer_email=customer_email,
      shipping_address=shipping_address,
      note=note,
      shipping_fee=0.0,
      discount_amount=0.0,
      currency='VND',
    )
    db.add(order)
    db.flush()

    for cart_item in cart_items:
      product = product_by_id.get(cart_item.product_id) if cart_item.product_id else None
      if not product:
        raise HTTPException(
          status_code=status.HTTP_409_CONFLICT,
          detail='Một hoặc nhiều sản phẩm trong giỏ hàng không còn tồn tại. Vui lòng tải lại giỏ hàng.',
        )

      stock_quantity = max(0, int(getattr(product, 'stock_quantity', 0) or 0))
      quantity = int(cart_item.quantity or 0)
      if quantity <= 0:
        continue
      if stock_quantity <= 0:
        raise HTTPException(
          status_code=status.HTTP_409_CONFLICT,
          detail=f'Sản phẩm "{product.name}" hiện đã hết hàng.',
        )
      if quantity > stock_quantity:
        raise HTTPException(
          status_code=status.HTTP_409_CONFLICT,
          detail=f'Sản phẩm "{product.name}" chỉ còn {stock_quantity} trong kho.',
        )

      product_name = _normalize_text(getattr(product, 'name', None)) or 'Sản phẩm không xác định'
      original_unit_price, sale_unit_price, unit_price = resolve_order_item_price_snapshot(product)
      line_total = round(unit_price * quantity, 2)
      subtotal_amount = round(subtotal_amount + line_total, 2)
      has_valid_items = True

      order_item = OrderItem(
        order_id=order.id,
        product_id=getattr(product, 'id', None),
        product_name=product_name,
        product_slug=_normalize_text(getattr(product, 'slug', None)) or None,
        product_sku=_normalize_text(getattr(product, 'sku', None)) or None,
        product_image_url=_normalize_text(getattr(product, 'image_url', None)) or None,
        original_unit_price=original_unit_price,
        sale_unit_price=sale_unit_price,
        unit_price=unit_price,
        quantity=quantity,
        line_total=line_total,
      )
      db.add(order_item)
      if payment_method != 'vnpay':
        product.stock_quantity = max(0, stock_quantity - quantity)

    if subtotal_amount <= 0 and not has_valid_items:
      raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail='Không có sản phẩm hợp lệ để tạo đơn hàng.',
      )

    order.subtotal_amount = subtotal_amount
    order.total_amount = round(subtotal_amount + order.shipping_fee - order.discount_amount, 2)

    should_finalize_inventory = payment_method != 'vnpay'
    if should_finalize_inventory:
      for cart_item in cart_items:
        db.delete(cart_item)

    db.commit()

    created_order = _get_order_with_items(db, order.id)
    if not created_order:
      raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail='Không thể tải đơn hàng vừa tạo.',
      )

    return _serialize_order(created_order)
  except HTTPException:
    db.rollback()
    raise
  except IntegrityError:
    db.rollback()
    duplicated_order = _get_existing_order_by_request_id(db, client_request_id)
    if duplicated_order and duplicated_order.user_id == user.id:
      return _serialize_order(duplicated_order)
    raise HTTPException(
      status_code=status.HTTP_409_CONFLICT,
      detail='Yêu cầu thanh toán đang được xử lý. Vui lòng tải lại lịch sử đơn hàng.',
    )
  except Exception as exc:
    db.rollback()
    logger.exception(
      'Checkout create_order_from_cart failed for user_id=%s client_request_id=%s payment_method=%s',
      getattr(user, 'id', None),
      client_request_id,
      payment_method,
    )
    detail = 'Không thể hoàn tất thanh toán. Hệ thống đã tự động khôi phục trạng thái trước đó.'
    if settings.debug:
      detail = f'{detail} Chi tiết kỹ thuật: {exc}'
    raise HTTPException(
      status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
      detail=detail,
    ) from exc


def get_user_orders(db: Session, user: User) -> OrderHistoryResponse:
  orders = db.scalars(
    select(Order)
    .where(Order.user_id == user.id)
    .options(selectinload(Order.items))
    .order_by(Order.placed_at.desc(), Order.id.desc()),
  ).all()

  items = [
    {
      'id': order.id,
      'code': order.code,
      'status': order.status,
      'status_label': _status_label(order.status),
      'payment_method': order.payment_method,
      'payment_method_label': _payment_method_label(order.payment_method),
      'payment_status': order.payment_status,
      'payment_status_label': _payment_status_label(order.payment_status),
      'customer_name': order.customer_name,
      'customer_phone': order.customer_phone,
      'customer_email': order.customer_email,
      'shipping_address': order.shipping_address,
      'subtotal_amount': _normalize_price(order.subtotal_amount),
      'shipping_fee': _normalize_price(order.shipping_fee),
      'discount_amount': _normalize_price(order.discount_amount),
      'total_amount': _normalize_price(order.total_amount),
      'currency': order.currency or 'VND',
      'item_count': sum(int(item.quantity or 0) for item in (order.items or [])),
      'placed_at': order.placed_at,
      'created_at': order.created_at,
      'updated_at': order.updated_at,
      'note': order.note or None,
      'items': [
        {
          'id': item.id,
          'product_id': item.product_id,
          'product_name': item.product_name,
          'product_slug': item.product_slug,
          'product_sku': item.product_sku,
          'product_image_url': item.product_image_url,
          'original_unit_price': _normalize_price(item.original_unit_price),
          'sale_unit_price': _normalize_price(item.sale_unit_price),
          'unit_price': _normalize_price(item.unit_price),
          'quantity': int(item.quantity or 0),
          'line_total': _normalize_price(item.line_total),
        }
        for item in (order.items or [])
      ],
    }
    for order in orders
  ]
  return OrderHistoryResponse(items=items, total=len(items))


def update_order_admin(db: Session, order_id: int, payload: OrderAdminWriteRequest) -> OrderRead:
  order = _get_order_with_items(db, order_id)
  if not order:
    raise HTTPException(
      status_code=status.HTTP_404_NOT_FOUND,
      detail='Không tìm thấy đơn hàng.',
    )

  has_changes = False
  next_status: str | None = None
  next_payment_status: str | None = None

  if payload.status is not None:
    next_status = _normalize_text(payload.status).lower()
    if next_status not in ORDER_STATUS_OPTIONS:
      raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail='Trạng thái đơn hàng không hợp lệ.',
      )
    _validate_order_status_transition(order.status, next_status)
    if order.status != next_status:
      order.status = next_status
      has_changes = True

  if payload.payment_status is not None:
    next_payment_status = _normalize_text(payload.payment_status).lower()
    _validate_payment_status(next_payment_status)
    if order.payment_status != next_payment_status:
      order.payment_status = next_payment_status
      has_changes = True

  is_cod_order = _normalize_text(order.payment_method).lower() == 'cod'
  should_auto_mark_cod_paid = (
    is_cod_order
    and next_status == 'delivered'
    and next_payment_status is None
    and order.payment_status != 'paid'
  )
  if should_auto_mark_cod_paid:
    order.payment_status = 'paid'
    has_changes = True

  if payload.note is not None:
    normalized_note = _normalize_text(payload.note) or None
    if order.note != normalized_note:
      order.note = normalized_note
      has_changes = True

  if not has_changes:
    return _serialize_order(order)

  db.add(order)
  db.commit()

  refreshed_order = _get_order_with_items(db, order.id)
  if not refreshed_order:
    raise HTTPException(
      status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
      detail='Không thể tải lại đơn hàng sau khi cập nhật.',
    )

  return _serialize_order(refreshed_order)


def finalize_vnpay_order_payment(db: Session, order: Order) -> OrderRead:
  if _normalize_text(order.payment_method).lower() != 'vnpay':
    raise HTTPException(
      status_code=status.HTTP_400_BAD_REQUEST,
      detail='Đơn hàng này không sử dụng thanh toán VNPAY.',
    )

  if order.payment_status == 'paid':
    refreshed_order = _get_order_with_items(db, order.id)
    if not refreshed_order:
      raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail='Không thể tải lại đơn hàng đã thanh toán.',
      )
    return _serialize_order(refreshed_order)

  try:
    product_ids = sorted({item.product_id for item in (order.items or []) if item.product_id})
    product_by_id = _get_locked_products_by_ids(db, product_ids)

    for order_item in order.items or []:
      if not order_item.product_id:
        continue

      product = product_by_id.get(order_item.product_id)
      if not product:
        raise HTTPException(
          status_code=status.HTTP_409_CONFLICT,
          detail=f'Sản phẩm "{order_item.product_name}" không còn tồn tại để hoàn tất thanh toán.',
        )

      stock_quantity = max(0, int(getattr(product, 'stock_quantity', 0) or 0))
      quantity = max(0, int(order_item.quantity or 0))
      if quantity <= 0:
        continue
      if stock_quantity < quantity:
        raise HTTPException(
          status_code=status.HTTP_409_CONFLICT,
          detail=f'Sản phẩm "{order_item.product_name}" không đủ tồn kho để hoàn tất thanh toán VNPAY.',
        )

      product.stock_quantity = stock_quantity - quantity

    _clear_user_cart_items(db, order.user_id)
    order.payment_status = 'paid'
    db.add(order)
    db.commit()
  except HTTPException:
    db.rollback()
    raise
  except Exception as exc:
    db.rollback()
    logger.exception('Finalize VNPAY payment failed for order_id=%s code=%s', order.id, order.code)
    detail = 'Không thể hoàn tất cập nhật thanh toán VNPAY.'
    if settings.debug:
      detail = f'{detail} Chi tiết kỹ thuật: {exc}'
    raise HTTPException(
      status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
      detail=detail,
    ) from exc

  refreshed_order = _get_order_with_items(db, order.id)
  if not refreshed_order:
    raise HTTPException(
      status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
      detail='Không thể tải lại đơn hàng sau khi xác nhận thanh toán VNPAY.',
    )
  return _serialize_order(refreshed_order)


def cancel_vnpay_order_payment(db: Session, order: Order) -> OrderRead:
  if _normalize_text(order.payment_method).lower() != 'vnpay':
    raise HTTPException(
      status_code=status.HTTP_400_BAD_REQUEST,
      detail='Đơn hàng này không sử dụng thanh toán VNPAY.',
    )

  if order.payment_status == 'paid':
    refreshed_order = _get_order_with_items(db, order.id)
    if not refreshed_order:
      raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail='Không thể tải lại đơn hàng đã thanh toán.',
      )
    return _serialize_order(refreshed_order)

  try:
    order.payment_status = 'failed'
    if order.status != 'cancelled':
      order.status = 'cancelled'
    db.add(order)
    db.commit()
  except Exception as exc:
    db.rollback()
    logger.exception('Cancel VNPAY payment failed for order_id=%s code=%s', order.id, order.code)
    detail = 'Không thể hủy giao dịch thanh toán VNPAY.'
    if settings.debug:
      detail = f'{detail} Chi tiết kỹ thuật: {exc}'
    raise HTTPException(
      status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
      detail=detail,
    ) from exc

  refreshed_order = _get_order_with_items(db, order.id)
  if not refreshed_order:
    raise HTTPException(
      status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
      detail='Không thể tải lại đơn hàng sau khi hủy giao dịch VNPAY.',
    )
  return _serialize_order(refreshed_order)
