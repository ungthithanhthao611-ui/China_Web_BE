from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import BigIntPrimaryKeyMixin, TimestampMixin

if TYPE_CHECKING:
    pass


class User(BigIntPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    username: Mapped[str | None] = mapped_column(String(100), unique=True, index=True)
    full_name: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(20))
    address: Mapped[str | None] = mapped_column(String(500))
    avatar_url: Mapped[str | None] = mapped_column(String(1000))
    role: Mapped[str] = mapped_column(String(50), default="user", index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    login_history: Mapped[list["UserLoginHistory"]] = relationship(
        "UserLoginHistory",
        back_populates="user",
        cascade="all, delete-orphan",
        order_by="desc(UserLoginHistory.login_at), desc(UserLoginHistory.id)",
    )


class UserLoginHistory(BigIntPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "user_login_history"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    login_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(128))
    user_agent: Mapped[str | None] = mapped_column(Text)
    login_method: Mapped[str] = mapped_column(String(50), default="password", nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="login_history")
