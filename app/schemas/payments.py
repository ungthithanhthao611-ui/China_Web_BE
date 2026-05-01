from pydantic import BaseModel, Field


class VnpayCreatePaymentRequest(BaseModel):
  order_id: int = Field(..., gt=0)
  return_url: str | None = Field(default=None, max_length=500)


class VnpayCreatePaymentResponse(BaseModel):
  order_id: int
  payment_url: str
  txn_ref: str


class VnpayReturnResponse(BaseModel):
  success: bool
  order_id: int | None = None
  order_code: str | None = None
  txn_ref: str | None = None
  response_code: str | None = None
  message: str | None = None
  payment_status: str | None = None
