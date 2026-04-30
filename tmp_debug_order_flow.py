from pprint import pprint
import traceback

import app.db.base  # noqa: F401
from sqlalchemy import text

from app.db.session import SessionLocal
from app.models.user import User
from app.schemas.orders import OrderCreateRequest
from app.services.orders import create_order_from_cart


def main():
  session = SessionLocal()
  try:
    print('=== schema defaults ===')
    rows = session.execute(
      text(
        """
        select table_name, column_name, column_default, is_nullable
        from information_schema.columns
        where table_name in ('orders', 'order_items')
          and column_name in ('id', 'created_at', 'updated_at', 'placed_at')
        order by table_name, ordinal_position
        """
      )
    )
    for row in rows:
      print(tuple(row))

    print('=== serial sequences ===')
    rows = session.execute(
      text(
        """
        select
          'orders' as table_name,
          pg_get_serial_sequence('orders', 'id') as seq
        union all
        select
          'order_items' as table_name,
          pg_get_serial_sequence('order_items', 'id') as seq
        """
      )
    )
    for row in rows:
      print(tuple(row))

    user = session.get(User, 3)
    print('=== user ===')
    print(user.id, user.username, user.email)

    payload = OrderCreateRequest(
      customer_name='Nguyễn Văn A',
      customer_phone='0359938475',
      customer_email='hellontt.nger1705@gmail.com',
      shipping_address='Số 2 Nguyễn Công Trứ, Phường Bình Thọ.',
      note='debug order',
      payment_method='cod',
      client_request_id='debug-checkout-request-99999',
    )

    print('=== creating order ===')
    result = create_order_from_cart(db=session, user=user, payload=payload)
    print('=== success ===')
    pprint(result.model_dump())
  except Exception as exc:
    print('=== exception ===')
    print(type(exc).__name__, exc)
    traceback.print_exc()
  finally:
    session.close()


if __name__ == '__main__':
  main()
