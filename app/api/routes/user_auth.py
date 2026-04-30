from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.security import decode_access_token
from app.models.user import User
from app.schemas.user import (
  UserCreate,
  UserLoginRequest,
  UserOrderHistoryResponse,
  UserPasswordChangeRequest,
  UserProfileUpdateRequest,
  UserRead,
  UserTokenResponse,
)
from app.services.media import create_uploaded_media_asset
from app.services.user_auth import (
  authenticate_user,
  change_user_password,
  get_user_order_history,
  register_user,
  serialize_user_profile,
  update_user_avatar,
  update_user_profile,
)
from fastapi.security import OAuth2PasswordBearer

router = APIRouter()
reusable_oauth2 = OAuth2PasswordBearer(tokenUrl='api/v1/user/auth/login')


def get_current_user(
  db: Session = Depends(get_db),
  token: str = Depends(reusable_oauth2),
) -> User:
  payload = decode_access_token(token)
  user_id = payload.get('sub')
  role = payload.get('role')
  if not user_id or role != 'user':
    from fastapi import HTTPException, status

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid token')

  user = db.scalar(select(User).where(User.id == int(user_id)))
  if not user:
    from fastapi import HTTPException, status

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='User not found')
  return user


@router.post('/register', response_model=UserRead)
def register(payload: UserCreate, db: Session = Depends(get_db)) -> UserRead:
  user = register_user(db=db, payload=payload)
  return serialize_user_profile(user)


@router.post('/login', response_model=UserTokenResponse)
def login(
  payload: UserLoginRequest,
  request: Request,
  db: Session = Depends(get_db),
) -> UserTokenResponse:
  return authenticate_user(db=db, payload=payload, request=request)


@router.get('/me', response_model=UserRead)
def me(current_user: User = Depends(get_current_user)) -> UserRead:
  return serialize_user_profile(current_user)


@router.put('/me', response_model=UserRead)
def update_me(
  payload: UserProfileUpdateRequest,
  db: Session = Depends(get_db),
  current_user: User = Depends(get_current_user),
) -> UserRead:
  return update_user_profile(db=db, user=current_user, payload=payload)


@router.post('/me/change-password')
def change_my_password(
  payload: UserPasswordChangeRequest,
  db: Session = Depends(get_db),
  current_user: User = Depends(get_current_user),
) -> dict[str, str]:
  change_user_password(db=db, user=current_user, payload=payload)
  return {'message': 'Đổi mật khẩu thành công.'}


@router.post('/me/avatar', response_model=UserRead)
async def upload_my_avatar(
  file: UploadFile = File(...),
  title: str | None = Form(default=None),
  db: Session = Depends(get_db),
  current_user: User = Depends(get_current_user),
) -> UserRead:
  media = await create_uploaded_media_asset(
    db=db,
    file=file,
    title=title or current_user.username or current_user.email,
    alt_text=current_user.full_name or current_user.username or current_user.email,
    asset_folder='users/avatars',
    public_id_base=f'user-{current_user.id}-avatar',
  )
  return update_user_avatar(db=db, user=current_user, avatar_url=media.get('url') or '')


@router.get('/me/orders', response_model=UserOrderHistoryResponse)
def my_order_history(
  db: Session = Depends(get_db),
  current_user: User = Depends(get_current_user),
) -> UserOrderHistoryResponse:
  return get_user_order_history(db=db, user=current_user)
