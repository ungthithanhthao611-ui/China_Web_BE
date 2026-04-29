from typing import Generator

from fastapi import Depends, Header, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.session import SessionLocal
from app.models.admin import AdminUser

bearer_scheme = HTTPBearer(auto_error=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_admin_user(
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> AdminUser:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer access token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_access_token(credentials.credentials)
    username = str(payload.get("sub") or "")
    user = db.scalar(select(AdminUser).where(AdminUser.username == username))
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin user is inactive or no longer exists.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def require_admin_user(current_user: AdminUser = Depends(get_current_admin_user)) -> AdminUser:
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role is required.",
        )
    return current_user


def get_language_code(
    language_code: str | None = Query(default=None),
    lang_header: str | None = Header(default=None, alias="lang"),
    accept_lang: str | None = Header(default=None, alias="Accept-Language"),
) -> str:
    """
    Detects language code from Query param or Header.
    Priority: Query > 'lang' Header > 'Accept-Language' Header > Default 'vi'
    """
    if language_code:
        return language_code
    if lang_header:
        return lang_header
    if accept_lang:
        # Simple extraction for 'en-US,en;q=0.9' -> 'en'
        return accept_lang.split(",")[0].split("-")[0].strip()
    return "vi"
