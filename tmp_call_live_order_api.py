import json
import urllib.error
import urllib.request

from app.core.security import create_access_token

payload = {
  'customer_name': 'Nguyễn Văn A',
  'customer_phone': '0359938475',
  'customer_email': 'hellontt.nger1705@gmail.com',
  'shipping_address': 'Số 2 Nguyễn Công Trứ, Phường Bình Thọ.',
  'note': 'live-http-debug',
  'payment_method': 'cod',
  'client_request_id': 'live-http-debug-12345678',
}

token = create_access_token('3', 'user')
request = urllib.request.Request(
  'http://127.0.0.1:8000/api/v1/user/orders/',
  data=json.dumps(payload).encode('utf-8'),
  headers={
    'Content-Type': 'application/json',
    'Accept': 'application/json',
    'Authorization': f'Bearer {token}',
  },
  method='POST',
)

try:
  with urllib.request.urlopen(request, timeout=20) as response:
    print('STATUS', response.status)
    print(response.read().decode('utf-8'))
except urllib.error.HTTPError as exc:
  print('HTTPERROR', exc.code)
  print(exc.read().decode('utf-8'))
except Exception as exc:
  print(type(exc).__name__, str(exc))
  raise
