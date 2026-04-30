from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User, UserLoginHistory
from app.schemas.user import (
  UserCreate,
  UserLoginHistoryRead,
  UserLoginRequest,
  UserPasswordChangeRequest,
  UserProfileUpdateRequest,
  UserRead,
  UserTokenResponse,
)
from app.services.orders import get_user_orders


def serialize_user_profile(user: User) -> UserRead:
  history_records = [
    UserLoginHistoryRead.model_validate(item, from_attributes=True)
    for item in (user.login_history or [])
  ]

  payload = UserRead.model_validate(user, from_attributes=True).model_dump()
  payload['login_history'] = [item.model_dump() for item in history_records]
  payload['login_history_count'] = len(history_records)
  return UserRead(**payload)


def register_user(db: Session, payload: UserCreate) -> User:
  existing_user = db.scalar(select(User).where(User.email == payload.email))
  if existing_user:
    raise HTTPException(
      status_code=status.HTTP_400_BAD_REQUEST,
      detail='Email already registered',
    )

  if payload.username:
    existing_username = db.scalar(select(User).where(User.username == payload.username))
    if existing_username:
      raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail='Username already taken',
      )

  new_user = User(
    email=payload.email,
    username=payload.username,
    full_name=payload.full_name,
    phone=payload.phone,
    address=payload.address,
    avatar_url=payload.avatar_url,
    role=(payload.role or 'user').strip() or 'user',
    password_hash=hash_password(payload.password),
    is_active=True,
  )
  db.add(new_user)
  db.commit()
  db.refresh(new_user)
  return new_user


def authenticate_user(
  db: Session,
  payload: UserLoginRequest,
  request: Request | None = None,
) -> UserTokenResponse:
  user = db.scalar(select(User).where(User.email == payload.email))
  if not user or not verify_password(payload.password, user.password_hash):
    raise HTTPException(
      status_code=status.HTTP_401_UNAUTHORIZED,
      detail='Invalid email or password',
    )

  if not user.is_active:
    raise HTTPException(
      status_code=status.HTTP_401_UNAUTHORIZED,
      detail='User account is disabled',
    )

  login_at = datetime.now(timezone.utc)
  user.last_login_at = login_at

  forwarded_for = (
    str(request.headers.get('x-forwarded-for', '')).split(',')[0].strip()
    if request
    else ''
  )
  client_host = (
    str(getattr(getattr(request, 'client', None), 'host', '') or '')
    if request
    else ''
  )
  ip_address = forwarded_for or client_host or None
  user_agent = str(request.headers.get('user-agent', '')).strip() if request else ''

  db.add(user)
  db.add(
    UserLoginHistory(
      user_id=user.id,
      login_at=login_at,
      ip_address=ip_address,
      user_agent=user_agent or None,
      login_method='password',
    ),
  )
  db.commit()
  db.refresh(user)

  access_token = create_access_token(
    subject=str(user.id),
    role='user',
    expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
  )
  return UserTokenResponse(
    access_token=access_token,
    token_type='bearer',
    expires_in=settings.access_token_expire_minutes * 60,
    user=serialize_user_profile(user),
  )


def update_user_profile(
  db: Session,
  user: User,
  payload: UserProfileUpdateRequest,
) -> UserRead:
  normalized_email = payload.email.strip().lower()
  existing_email = db.scalar(
    select(User).where(User.email == normalized_email, User.id != user.id),
  )
  if existing_email:
    raise HTTPException(
      status_code=status.HTTP_400_BAD_REQUEST,
      detail='Email đã được sử dụng bởi tài khoản khác.',
    )

  normalized_username = str(payload.username or '').strip() or None
  if normalized_username:
    existing_username = db.scalar(
      select(User).where(User.username == normalized_username, User.id != user.id),
    )
    if existing_username:
      raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail='Tên đăng nhập đã tồn tại.',
      )

  user.email = normalized_email
  user.username = normalized_username
  user.full_name = str(payload.full_name or '').strip() or None
  user.phone = str(payload.phone or '').strip() or None
  user.address = str(payload.address or '').strip() or None

  db.add(user)
  db.commit()
  db.refresh(user)
  return serialize_user_profile(user)


def update_user_avatar(db: Session, user: User, avatar_url: str) -> UserRead:
  normalized_avatar = str(avatar_url or '').strip()
  if not normalized_avatar:
    raise HTTPException(
      status_code=status.HTTP_400_BAD_REQUEST,
      detail='Avatar URL không hợp lệ.',
    )

  user.avatar_url = normalized_avatar
  db.add(user)
  db.commit()
  db.refresh(user)
  return serialize_user_profile(user)


def change_user_password(
  db: Session,
  user: User,
  payload: UserPasswordChangeRequest,
) -> None:
  if not verify_password(payload.current_password, user.password_hash):
    raise HTTPException(
      status_code=status.HTTP_400_BAD_REQUEST,
      detail='Mật khẩu hiện tại không chính xác.',
    )

  if payload.new_password != payload.confirm_password:
    raise HTTPException(
      status_code=status.HTTP_400_BAD_REQUEST,
      detail='Mật khẩu mới và xác nhận mật khẩu không khớp.',
    )

  if payload.current_password == payload.new_password:
    raise HTTPException(
      status_code=status.HTTP_400_BAD_REQUEST,
      detail='Mật khẩu mới phải khác mật khẩu hiện tại.',
    )

  user.password_hash = hash_password(payload.new_password)
  db.add(user)
  db.commit()


def get_user_order_history(db: Session, user: User):
  return get_user_orders(db=db, user=user)
