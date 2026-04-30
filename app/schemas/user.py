from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class UserBase(BaseModel):
  email: EmailStr
  username: str | None = None
  full_name: str | None = None
  phone: str | None = None
  address: str | None = None
  avatar_url: str | None = None
  role: str = 'user'


class UserCreate(UserBase):
  password: str = Field(..., min_length=6)
  is_active: bool = True


class UserUpdate(BaseModel):
  email: EmailStr | None = None
  username: str | None = None
  full_name: str | None = None
  phone: str | None = None
  address: str | None = None
  avatar_url: str | None = None
  role: str | None = None
  password: str | None = Field(None, min_length=6)
  is_active: bool | None = None


class UserProfileUpdateRequest(BaseModel):
  email: EmailStr
  username: str | None = None
  full_name: str | None = None
  phone: str | None = None
  address: str | None = None


class UserPasswordChangeRequest(BaseModel):
  current_password: str = Field(..., min_length=6)
  new_password: str = Field(..., min_length=6)
  confirm_password: str = Field(..., min_length=6)


class UserLoginHistoryRead(BaseModel):
  id: int
  user_id: int
  login_at: datetime
  ip_address: str | None = None
  user_agent: str | None = None
  login_method: str
  created_at: datetime
  updated_at: datetime | None = None

  class Config:
    from_attributes = True


class UserOrderItemRead(BaseModel):
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


class UserOrderHistoryItemRead(BaseModel):
  id: int
  code: str
  status: str
  status_label: str | None = None
  payment_method: str = 'cod'
  payment_method_label: str | None = None
  payment_status: str = 'unpaid'
  payment_status_label: str | None = None
  customer_name: str
  customer_phone: str
  customer_email: str
  shipping_address: str
  subtotal_amount: float = 0.0
  shipping_fee: float = 0.0
  discount_amount: float = 0.0
  total_amount: float
  currency: str = 'VND'
  item_count: int = 0
  placed_at: datetime | None = None
  created_at: datetime | None = None
  updated_at: datetime | None = None
  note: str | None = None
  items: list[UserOrderItemRead] = Field(default_factory=list)


class UserOrderHistoryResponse(BaseModel):
  items: list[UserOrderHistoryItemRead] = Field(default_factory=list)
  total: int = 0


class UserRead(UserBase):
  id: int
  is_active: bool
  created_at: datetime
  updated_at: datetime | None = None
  last_login_at: datetime | None = None
  login_history: list[UserLoginHistoryRead] = Field(default_factory=list)
  login_history_count: int = 0

  class Config:
    from_attributes = True


class UserLoginRequest(BaseModel):
  email: EmailStr
  password: str


class UserTokenResponse(BaseModel):
  access_token: str
  token_type: str = 'bearer'
  expires_in: int
  user: UserRead
