from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.routes.user_auth import get_current_user
from app.models.user import User
from app.schemas.payments import (
  VnpayCreatePaymentRequest,
  VnpayCreatePaymentResponse,
  VnpayReturnResponse,
)
from app.services.orders import (
  cancel_vnpay_order_payment,
  finalize_vnpay_order_payment,
  get_order_by_code,
  get_user_order_by_id,
)
from app.services.vnpay import build_payment_url, resolve_client_ip, verify_response_params

router = APIRouter()


@router.post('/create', response_model=VnpayCreatePaymentResponse)
def create_vnpay_payment(
  payload: VnpayCreatePaymentRequest,
  request: Request,
  db: Session = Depends(get_db),
  current_user: User = Depends(get_current_user),
) -> VnpayCreatePaymentResponse:
  order = get_user_order_by_id(db=db, user_id=current_user.id, order_id=payload.order_id)
  if not order:
    raise HTTPException(
      status_code=status.HTTP_404_NOT_FOUND,
      detail='Không tìm thấy đơn hàng.',
    )

  if order.payment_method != 'vnpay':
    raise HTTPException(
      status_code=status.HTTP_400_BAD_REQUEST,
      detail='Đơn hàng này không sử dụng phương thức thanh toán VNPAY.',
    )

  if order.payment_status == 'paid':
    raise HTTPException(
      status_code=status.HTTP_409_CONFLICT,
      detail='Đơn hàng đã được thanh toán trước đó.',
    )

  if order.total_amount <= 0:
    raise HTTPException(
      status_code=status.HTTP_409_CONFLICT,
      detail='Đơn hàng không hợp lệ để khởi tạo thanh toán VNPAY.',
    )

  payment_url = build_payment_url(
    txn_ref=order.code,
    amount=order.total_amount,
    order_info=f'Thanh toan don hang {order.code}',
    client_ip=resolve_client_ip(request),
    return_url=payload.return_url,
  )

  return VnpayCreatePaymentResponse(
    order_id=order.id,
    payment_url=payment_url,
    txn_ref=order.code,
  )


@router.get('/return', response_model=VnpayReturnResponse)
def verify_vnpay_return(
  request: Request,
  db: Session = Depends(get_db),
) -> VnpayReturnResponse:
  query_params = {key: value for key, value in request.query_params.items()}
  is_valid = verify_response_params(query_params, context='return')
  txn_ref = str(query_params.get('vnp_TxnRef', '') or '').strip()
  response_code = str(query_params.get('vnp_ResponseCode', '') or '').strip()
  order = get_order_by_code(db=db, code=txn_ref) if txn_ref else None

  success = bool(is_valid and response_code == '00' and order)
  if order:
    if success:
      updated_order = finalize_vnpay_order_payment(db=db, order=order)
    else:
      updated_order = cancel_vnpay_order_payment(db=db, order=order)
  else:
    updated_order = None

  message = 'Thanh toán thành công.' if success else 'Thanh toán đã bị hủy hoặc thất bại.'

  return VnpayReturnResponse(
    success=success,
    order_id=getattr(updated_order, 'id', None) if updated_order else getattr(order, 'id', None),
    order_code=getattr(updated_order, 'code', None) if updated_order else getattr(order, 'code', None),
    txn_ref=txn_ref or None,
    response_code=response_code or None,
    message=message,
    payment_status=getattr(updated_order, 'payment_status', None) if updated_order else getattr(order, 'payment_status', None),
  )


@router.get('/ipn')
def handle_vnpay_ipn(
  request: Request,
  db: Session = Depends(get_db),
) -> dict[str, str]:
  query_params = {key: value for key, value in request.query_params.items()}
  if not verify_response_params(query_params, context='ipn'):
    return {'RspCode': '97', 'Message': 'Invalid checksum'}

  txn_ref = str(query_params.get('vnp_TxnRef', '') or '').strip()
  response_code = str(query_params.get('vnp_ResponseCode', '') or '').strip()
  order = get_order_by_code(db=db, code=txn_ref)

  if not order:
    return {'RspCode': '01', 'Message': 'Order not found'}

  if response_code == '00':
    finalize_vnpay_order_payment(db=db, order=order)
  else:
    cancel_vnpay_order_payment(db=db, order=order)

  return {'RspCode': '00', 'Message': 'Confirm Success'}
