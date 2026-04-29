from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.user import UserCreate, UserLoginRequest, UserRead, UserTokenResponse
from app.services.user_auth import authenticate_user, register_user
from app.core.security import decode_access_token
from fastapi.security import OAuth2PasswordBearer
from app.models.user import User
from sqlalchemy import select

router = APIRouter()
reusable_oauth2 = OAuth2PasswordBearer(tokenUrl="api/v1/user/auth/login")

def get_current_user(db: Session = Depends(get_db), token: str = Depends(reusable_oauth2)) -> User:
    payload = decode_access_token(token)
    user_id = payload.get("sub")
    role = payload.get("role")
    if not user_id or role != "user":
        from fastapi import HTTPException, status
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    
    user = db.scalar(select(User).where(User.id == int(user_id)))
    if not user:
        from fastapi import HTTPException, status
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.post("/register", response_model=UserRead)
def register(payload: UserCreate, db: Session = Depends(get_db)) -> UserRead:
    return register_user(db=db, payload=payload)


@router.post("/login", response_model=UserTokenResponse)
def login(payload: UserLoginRequest, db: Session = Depends(get_db)) -> UserTokenResponse:
    return authenticate_user(db=db, payload=payload)


@router.get("/me", response_model=UserRead)
def me(current_user: User = Depends(get_current_user)) -> UserRead:
    return UserRead.model_validate(current_user, from_attributes=True)
