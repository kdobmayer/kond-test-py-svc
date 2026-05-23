from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field, field_validator


# --- Merchant Schemas ---

class MerchantCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    email: str = Field(..., max_length=255)
    currency: str = Field(default="USD", max_length=3)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("Invalid email format")
        return v.lower()


class MerchantUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    email: Optional[str] = Field(None, max_length=255)
    is_active: Optional[bool] = None

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and ("@" not in v or "." not in v.split("@")[-1]):
            raise ValueError("Invalid email format")
        return v.lower() if v else v


class MerchantResponse(BaseModel):
    id: str
    name: str
    email: str
    api_key: str
    balance: float
    currency: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MerchantListResponse(BaseModel):
    merchants: list["MerchantResponse"]
    total: int


# --- Payment Schemas ---

class PaymentCreate(BaseModel):
    merchant_id: str
    amount: float = Field(..., gt=0, le=999999.99)
    currency: str = Field(default="USD", max_length=3)
    description: Optional[str] = None
    customer_email: Optional[str] = None
    idempotency_key: Optional[str] = Field(None, max_length=255)
    metadata: Optional[dict] = None

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Amount must be positive")
        if round(v, 2) != v:
            raise ValueError("Amount must have at most 2 decimal places")
        return v

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, v: str) -> str:
        allowed = {"USD", "EUR", "GBP", "CAD", "AUD"}
        if v.upper() not in allowed:
            raise ValueError(f"Currency must be one of: {', '.join(sorted(allowed))}")
        return v.upper()


class PaymentCaptureRequest(BaseModel):
    amount: Optional[float] = Field(None, gt=0)

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and v <= 0:
            raise ValueError("Capture amount must be positive")
        return v


class PaymentResponse(BaseModel):
    id: str
    merchant_id: str
    amount: float
    currency: str
    status: str
    description: Optional[str]
    customer_email: Optional[str]
    idempotency_key: Optional[str]
    captured_amount: float
    refunded_amount: float
    failure_reason: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PaymentListResponse(BaseModel):
    payments: list[PaymentResponse]
    total: int


# --- Refund Schemas ---

class RefundCreate(BaseModel):
    amount: float = Field(..., gt=0, le=999999.99)
    reason: Optional[str] = None

    # Intentional duplication: same validation as PaymentCreate.amount
    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Amount must be positive")
        if round(v, 2) != v:
            raise ValueError("Amount must have at most 2 decimal places")
        return v


class RefundResponse(BaseModel):
    id: str
    payment_id: str
    amount: float
    reason: Optional[str]
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


# --- Webhook Schemas ---

class WebhookEndpointCreate(BaseModel):
    merchant_id: str
    url: str = Field(..., max_length=2048)
    events: list[str] = Field(..., min_length=1)

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")
        return v

    @field_validator("events")
    @classmethod
    def validate_events(cls, v: list[str]) -> list[str]:
        valid_events = {
            "payment.created", "payment.captured", "payment.voided",
            "payment.refunded", "merchant.created", "settlement.completed",
        }
        for event in v:
            if event not in valid_events:
                raise ValueError(f"Invalid event type: {event}")
        return v


class WebhookEndpointUpdate(BaseModel):
    url: Optional[str] = Field(None, max_length=2048)
    events: Optional[list[str]] = None
    is_active: Optional[bool] = None


class WebhookEndpointResponse(BaseModel):
    id: str
    merchant_id: str
    url: str
    events: list[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class WebhookDeliveryResponse(BaseModel):
    id: str
    endpoint_id: str
    event_type: str
    payload: str
    status: str
    response_code: Optional[int]
    attempts: int
    last_attempt_at: Optional[datetime]
    delivered_at: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}


class WebhookVerifyRequest(BaseModel):
    payload: str
    signature: str
    secret: str


class WebhookVerifyResponse(BaseModel):
    valid: bool


# --- Report Schemas ---

class TransactionSummary(BaseModel):
    merchant_id: str
    period_start: datetime
    period_end: datetime
    total_payments: int
    total_amount: float
    captured_amount: float
    refunded_amount: float
    voided_count: int
    average_payment: float
    currency: str


class SettlementReport(BaseModel):
    id: str
    merchant_id: str
    total_amount: float
    fee_amount: float
    net_amount: float
    payment_count: int
    refund_count: int
    period_start: datetime
    period_end: datetime
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class SettlementListResponse(BaseModel):
    settlements: list[SettlementReport]
    total: int


# --- Metrics Schema ---

class MetricsResponse(BaseModel):
    total_payments: int
    total_merchants: int
    total_webhooks_delivered: int
