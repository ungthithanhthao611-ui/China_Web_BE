from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BIGINT_TYPE


class BigIntPrimaryKeyMixin:
    id: Mapped[int] = mapped_column(BIGINT_TYPE, primary_key=True, autoincrement=True)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class SortOrderMixin:
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class StatusMixin:
    status: Mapped[str] = mapped_column(String(50), default="active", index=True, nullable=False)
