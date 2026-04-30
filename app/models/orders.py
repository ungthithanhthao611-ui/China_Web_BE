from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import BigIntPrimaryKeyMixin, TimestampMixin

if TYPE_CHECKING:
  from app.models.user import User


class Order(BigIntPrimaryKeyMixin, TimestampMixin, Base):
  __tablename__ = 'orders'

  user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
  code: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
  client_request_id: Mapped[str | None] = mapped_column(String(100), unique=True, index=True)
  status: Mapped[str] = mapped_column(String(50), default='pending_confirmation', index=True, nullable=False)
  payment_method: Mapped[str] = mapped_column(String(50), default='cod', index=True, nullable=False)
  payment_status: Mapped[str] = mapped_column(String(50), default='unpaid', index=True, nullable=False)
  customer_name: Mapped[str] = mapped_column(String(255), nullable=False)
  customer_phone: Mapped[str] = mapped_column(String(50), nullable=False)
  customer_email: Mapped[str] = mapped_column(String(255), nullable=False)
  shipping_address: Mapped[str] = mapped_column(Text, nullable=False)
  note: Mapped[str | None] = mapped_column(Text)
  subtotal_amount: Mapped[float] = mapped_column(default=0.0, nullable=False)
  shipping_fee: Mapped[float] = mapped_column(default=0.0, nullable=False)
  discount_amount: Mapped[float] = mapped_column(default=0.0, nullable=False)
  total_amount: Mapped[float] = mapped_column(default=0.0, nullable=False)
  currency: Mapped[str] = mapped_column(String(10), default='VND', nullable=False)
  placed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

  user: Mapped['User'] = relationship('User')
  items: Mapped[list['OrderItem']] = relationship(
    'OrderItem',
    back_populates='order',
    cascade='all, delete-orphan',
    order_by='OrderItem.id',
  )


class OrderItem(BigIntPrimaryKeyMixin, TimestampMixin, Base):
  __tablename__ = 'order_items'

  order_id: Mapped[int] = mapped_column(ForeignKey('orders.id', ondelete='CASCADE'), nullable=False, index=True)
  product_id: Mapped[int | None] = mapped_column(ForeignKey('products.id', ondelete='SET NULL'), index=True)
  product_name: Mapped[str] = mapped_column(String(255), nullable=False)
  product_slug: Mapped[str | None] = mapped_column(String(255), index=True)
  product_sku: Mapped[str | None] = mapped_column(String(100))
  product_image_url: Mapped[str | None] = mapped_column(String(2000))
  original_unit_price: Mapped[float] = mapped_column(default=0.0, nullable=False)
  sale_unit_price: Mapped[float] = mapped_column(default=0.0, nullable=False)
  unit_price: Mapped[float] = mapped_column(default=0.0, nullable=False)
  quantity: Mapped[int] = mapped_column(default=1, nullable=False)
  line_total: Mapped[float] = mapped_column(default=0.0, nullable=False)

  order: Mapped['Order'] = relationship('Order', back_populates='items')
