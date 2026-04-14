from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import BigIntPrimaryKeyMixin, TimestampMixin


class Menu(BigIntPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "menus"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    location: Mapped[str | None] = mapped_column(String(100), index=True)
    language_id: Mapped[int] = mapped_column(ForeignKey("languages.id"), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    language = relationship("Language")
    items: Mapped[list["MenuItem"]] = relationship(back_populates="menu", cascade="all, delete-orphan")


class MenuItem(BigIntPrimaryKeyMixin, Base):
    __tablename__ = "menu_items"

    menu_id: Mapped[int] = mapped_column(ForeignKey("menus.id"), nullable=False)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("menu_items.id"))
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    target: Mapped[str | None] = mapped_column(String(20))
    item_type: Mapped[str | None] = mapped_column(String(50), index=True)
    page_id: Mapped[int | None] = mapped_column(ForeignKey("pages.id"))
    anchor: Mapped[str | None] = mapped_column(String(100))
    sort_order: Mapped[int] = mapped_column(default=0, index=True, nullable=False)

    menu: Mapped["Menu"] = relationship(back_populates="items")
