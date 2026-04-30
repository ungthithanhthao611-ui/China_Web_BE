from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class OrderItemRead(BaseModel):
  model_config = ConfigDict(from_attributes=True)

  id: int
  product_id: int | None = None
  product_name: str
  product_slug: str | None = None
  product_sku: str | None = None
  product_image_url: str | None = None
  original_unit_price: float = 0.0
  sale_unit_price: float = 0.0
  unit_price: float = 0.0
  quantity: int = 0
  line_total: float = 0.0


class OrderRead(BaseModel):
  model_config = ConfigDict(from_attributes=True)

  id: int
  code: str
  client_request_id: str | None = None
  user_id: int
  status: str
  status_label: str | None = None
  payment_method: str
  payment_method_label: str | None = None
  payment_status: str
  payment_status_label: str | None = None
  customer_name: str
  customer_phone: str
  customer_email: str
  shipping_address: str
  note: str | None = None
  subtotal_amount: float = 0.0
  shipping_fee: float = 0.0
  discount_amount: float = 0.0
  total_amount: float = 0.0
  currency: str = 'VND'
  item_count: int = 0
  placed_at: datetime | None = None
  created_at: datetime | None = None
  updated_at: datetime | None = None
  items: list[OrderItemRead] = Field(default_factory=list)


class OrderCreateRequest(BaseModel):
  customer_name: str = Field(..., min_length=2, max_length=255)
  customer_phone: str = Field(..., min_length=6, max_length=50)
  customer_email: str = Field(..., min_length=5, max_length=255)
  shipping_address: str = Field(..., min_length=5, max_length=2000)
  note: str | None = Field(default=None, max_length=4000)
  payment_method: str = Field(default='cod', min_length=3, max_length=50)
  client_request_id: str = Field(..., min_length=8, max_length=100)


class OrderAdminWriteRequest(BaseModel):
  status: str | None = Field(default=None, min_length=3, max_length=50)
  payment_status: str | None = Field(default=None, min_length=3, max_length=50)
  note: str | None = Field(default=None, max_length=4000)


class OrderHistoryItemRead(BaseModel):
  id: int
  code: str
  status: str
  status_label: str | None = None
  payment_method: str
  payment_method_label: str | None = None
  payment_status: str
  payment_status_label: str | None = None
  customer_name: str
  customer_phone: str
  customer_email: str
  shipping_address: str
  subtotal_amount: float = 0.0
  shipping_fee: float = 0.0
  discount_amount: float = 0.0
  total_amount: float = 0.0
  currency: str = 'VND'
  item_count: int = 0
  placed_at: datetime | None = None
  created_at: datetime | None = None
  updated_at: datetime | None = None
  note: str | None = None
  items: list[OrderItemRead] = Field(default_factory=list)


class OrderHistoryResponse(BaseModel):
  items: list[OrderHistoryItemRead] = Field(default_factory=list)
  total: int = 0
