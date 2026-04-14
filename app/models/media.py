from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BIGINT_TYPE, Base
from app.models.mixins import BigIntPrimaryKeyMixin, TimestampMixin


class MediaAsset(BigIntPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "media_assets"

    uuid: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    file_name: Mapped[str | None] = mapped_column(String(255))
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    storage_path: Mapped[str | None] = mapped_column(String(1000))
    asset_type: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(100))
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    size: Mapped[int | None] = mapped_column(Integer)
    alt_text: Mapped[str | None] = mapped_column(String(255))
    title: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(50), default="active", index=True, nullable=False)


class EntityMedia(BigIntPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "entity_media"

    entity_type: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    entity_id: Mapped[int] = mapped_column(BIGINT_TYPE, index=True, nullable=False)
    media_id: Mapped[int] = mapped_column(ForeignKey("media_assets.id"), nullable=False)
    group_name: Mapped[str] = mapped_column(String(100), default="default", index=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(default=0, nullable=False)
    caption: Mapped[str | None] = mapped_column(String(255))

    media: Mapped["MediaAsset"] = relationship()
