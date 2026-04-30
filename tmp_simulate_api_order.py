import app.db.base  # noqa: F401
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.user import User
from app.schemas.orders import OrderCreateRequest
from app.services.orders import create_order_from_cart


def main():
  session = SessionLocal()
  try:
    user = session.scalar(select(User).where(User.id == 3))
    payload = OrderCreateRequest(
      customer_name='Nguyễn Văn A',
      customer_phone='0359938475',
      customer_email='hellontt.nger1705@gmail.com',
      shipping_address='Số 2 Nguyễn Công Trứ, Phường Bình Thọ.',
      note='debug api-like order',
      payment_method='cod',
      client_request_id='debug-api-like-request-123456',
    )
    result = create_order_from_cart(db=session, user=user, payload=payload)
    print('SUCCESS', result.code, result.id, result.total_amount)
  except Exception as exc:
    print(type(exc).__name__, exc)
    raise
  finally:
    session.close()


if __name__ == '__main__':
  main()
