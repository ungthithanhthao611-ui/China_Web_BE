from __future__ import annotations

import hashlib
import hmac
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from ipaddress import ip_address
from urllib.parse import urlencode

from fastapi import HTTPException, Request, status

from app.core.config import get_settings


def _runtime_settings():
  get_settings.cache_clear()
  return get_settings()


def _normalize_params(params: dict[str, object]) -> dict[str, str]:
  return {
    key: str(value)
    for key, value in sorted(params.items(), key=lambda item: item[0])
    if value is not None and str(value) != ''
  }


def _build_hash_payload(params: dict[str, str]) -> str:
  return '&'.join(f'{key}={value}' for key, value in params.items())


def _strip_accents(value: str) -> str:
  normalized = unicodedata.normalize('NFKD', value or '')
  return ''.join(character for character in normalized if not unicodedata.combining(character))


def normalize_vnpay_text(value: str, fallback: str) -> str:
  ascii_text = _strip_accents(str(value or fallback))
  sanitized = re.sub(r'[^A-Za-z0-9\s:_-]', ' ', ascii_text)
  compact = re.sub(r'\s+', ' ', sanitized).strip()
  return compact[:255] or fallback


def normalize_vnpay_txn_ref(value: str) -> str:
  ascii_text = _strip_accents(str(value or ''))
  compact = re.sub(r'[^A-Za-z0-9]', '', ascii_text).upper()
  return compact[:100]


def _validate_vnpay_settings() -> None:
  runtime_settings = _runtime_settings()
  missing_keys = []
  if not runtime_settings.vnpay_tmn_code:
    missing_keys.append('VNPAY_TMN_CODE')
  if not runtime_settings.vnpay_hash_secret:
    missing_keys.append('VNPAY_HASH_SECRET')
  if not runtime_settings.vnpay_return_url:
    missing_keys.append('VNPAY_RETURN_URL')


  if missing_keys:
    raise HTTPException(
      status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
      detail=f'Thiếu cấu hình VNPAY bắt buộc: {", ".join(missing_keys)}.',
    )


def create_secure_hash(params: dict[str, object]) -> str:
  runtime_settings = _runtime_settings()
  normalized_params = _normalize_params(params)
  payload = _build_hash_payload(normalized_params)
  return hmac.new(
    runtime_settings.vnpay_hash_secret.encode('utf-8'),
    payload.encode('utf-8'),
    hashlib.sha512,
  ).hexdigest()


def build_payment_url(*, txn_ref: str, amount: float, order_info: str, client_ip: str) -> str:
  _validate_vnpay_settings()
  runtime_settings = _runtime_settings()

  normalized_txn_ref = normalize_vnpay_txn_ref(txn_ref)
  if not normalized_txn_ref:
    raise HTTPException(
      status_code=status.HTTP_400_BAD_REQUEST,
      detail='Mã giao dịch VNPAY không hợp lệ.',
    )

  now = datetime.now(timezone(timedelta(hours=7)))
  create_date = now.strftime('%Y%m%d%H%M%S')
  expire_date = (now + timedelta(minutes=15)).strftime('%Y%m%d%H%M%S')

  params: dict[str, object] = {
    'vnp_Version': runtime_settings.vnpay_version,
    'vnp_Command': runtime_settings.vnpay_command,
    'vnp_TmnCode': runtime_settings.vnpay_tmn_code,
    'vnp_Amount': int(round(float(amount) * 100)),
    'vnp_CurrCode': runtime_settings.vnpay_curr_code,
    'vnp_TxnRef': normalized_txn_ref,
    'vnp_OrderInfo': normalize_vnpay_text(order_info, 'Thanh toan don hang'),
    'vnp_OrderType': 'other',
    'vnp_Locale': runtime_settings.vnpay_locale,
    'vnp_ReturnUrl': runtime_settings.vnpay_return_url,
    'vnp_IpAddr': client_ip,
    'vnp_CreateDate': create_date,
    'vnp_ExpireDate': expire_date,
  }

  normalized_params = _normalize_params(params)
  normalized_params['vnp_SecureHash'] = create_secure_hash(normalized_params)
  return f"{runtime_settings.vnpay_payment_url}?{urlencode(normalized_params)}"


def verify_response_params(query_params: dict[str, str]) -> bool:
  payload = dict(query_params)
  received_hash = str(payload.pop('vnp_SecureHash', '') or '')
  payload.pop('vnp_SecureHashType', None)
  if not received_hash:
    return False
  expected_hash = create_secure_hash(payload)
  return hmac.compare_digest(received_hash, expected_hash)


def resolve_client_ip(request: Request) -> str:
  forwarded_for = request.headers.get('x-forwarded-for', '')
  candidate = forwarded_for.split(',')[0].strip() if forwarded_for else ''
  if not candidate and request.client:
    candidate = request.client.host or ''

  try:
    ip_address(candidate)
    return candidate
  except ValueError:
    return '127.0.0.1'
