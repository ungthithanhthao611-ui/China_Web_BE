from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BIGINT_TYPE, Base, SMALLINT_TYPE
from app.models.mixins import BigIntPrimaryKeyMixin, TimestampMixin


class Language(Base):
    __tablename__ = "languages"

    id: Mapped[int] = mapped_column(SMALLINT_TYPE, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_default: Mapped[bool] = mapped_column(default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="active", index=True, nullable=False)


class Translation(BigIntPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "translations"

    language_id: Mapped[int] = mapped_column(ForeignKey("languages.id"), index=True, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    entity_id: Mapped[int] = mapped_column(BIGINT_TYPE, index=True, nullable=False)
    field_name: Mapped[str] = mapped_column(String(100), nullable=False)
    translated_text: Mapped[str] = mapped_column(Text, nullable=False)

    language: Mapped["Language"] = relationship()


class SiteSetting(BigIntPrimaryKeyMixin, Base):
    __tablename__ = "site_settings"

    config_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    config_value: Mapped[str | None] = mapped_column(Text)
    language_id: Mapped[int | None] = mapped_column(ForeignKey("languages.id"))
    group_name: Mapped[str | None] = mapped_column(String(100), index=True)
    description: Mapped[str | None] = mapped_column(String(255))
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    language: Mapped["Language | None"] = relationship()
