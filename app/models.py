import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Float, DateTime, ForeignKey, Text, Boolean, Enum as SAEnum
from sqlalchemy.orm import relationship
import enum

from app.database import Base


def utcnow():
    return datetime.now(timezone.utc)


def gen_uuid():
    return str(uuid.uuid4())


class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    AUTHORIZED = "authorized"
    CAPTURED = "captured"
    VOIDED = "voided"
    REFUNDED = "refunded"
    PARTIALLY_REFUNDED = "partially_refunded"
    FAILED = "failed"


class WebhookEventType(str, enum.Enum):
    PAYMENT_CREATED = "payment.created"
    PAYMENT_CAPTURED = "payment.captured"
    PAYMENT_VOIDED = "payment.voided"
    PAYMENT_REFUNDED = "payment.refunded"
    MERCHANT_CREATED = "merchant.created"
    SETTLEMENT_COMPLETED = "settlement.completed"


class DeliveryStatus(str, enum.Enum):
    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"


class Merchant(Base):
    __tablename__ = "merchants"

    id = Column(String, primary_key=True, default=gen_uuid)
    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False, unique=True)
    api_key = Column(String(64), nullable=False, unique=True)
    api_secret = Column(String(128), nullable=False)
    balance = Column(Float, default=0.0)
    currency = Column(String(3), default="USD")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    payments = relationship("Payment", back_populates="merchant")
    webhook_endpoints = relationship("WebhookEndpoint", back_populates="merchant")
    settlements = relationship("Settlement", back_populates="merchant")


class Payment(Base):
    __tablename__ = "payments"

    id = Column(String, primary_key=True, default=gen_uuid)
    merchant_id = Column(String, ForeignKey("merchants.id"), nullable=False)
    amount = Column(Float, nullable=False)
    currency = Column(String(3), default="USD")
    status = Column(SAEnum(PaymentStatus), default=PaymentStatus.PENDING)
    description = Column(Text, nullable=True)
    customer_email = Column(String(255), nullable=True)
    idempotency_key = Column(String(255), nullable=True, unique=True)
    metadata_json = Column(Text, nullable=True)
    captured_amount = Column(Float, default=0.0)
    refunded_amount = Column(Float, default=0.0)
    failure_reason = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    merchant = relationship("Merchant", back_populates="payments")
    refunds = relationship("Refund", back_populates="payment")


class Refund(Base):
    __tablename__ = "refunds"

    id = Column(String, primary_key=True, default=gen_uuid)
    payment_id = Column(String, ForeignKey("payments.id"), nullable=False)
    amount = Column(Float, nullable=False)
    reason = Column(Text, nullable=True)
    status = Column(String(20), default="completed")
    created_at = Column(DateTime, default=utcnow)

    payment = relationship("Payment", back_populates="refunds")


class WebhookEndpoint(Base):
    __tablename__ = "webhook_endpoints"

    id = Column(String, primary_key=True, default=gen_uuid)
    merchant_id = Column(String, ForeignKey("merchants.id"), nullable=False)
    url = Column(String(2048), nullable=False)
    secret = Column(String(128), nullable=False)
    events = Column(Text, nullable=False)  # JSON list of event types
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    merchant = relationship("Merchant", back_populates="webhook_endpoints")
    deliveries = relationship("WebhookDelivery", back_populates="endpoint")


class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"

    id = Column(String, primary_key=True, default=gen_uuid)
    endpoint_id = Column(String, ForeignKey("webhook_endpoints.id"), nullable=False)
    event_type = Column(String(50), nullable=False)
    payload = Column(Text, nullable=False)
    status = Column(SAEnum(DeliveryStatus), default=DeliveryStatus.PENDING)
    response_code = Column(Integer, nullable=True)
    attempts = Column(Integer, default=0)
    last_attempt_at = Column(DateTime, nullable=True)
    delivered_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow)

    endpoint = relationship("WebhookEndpoint", back_populates="deliveries")


class Settlement(Base):
    __tablename__ = "settlements"

    id = Column(String, primary_key=True, default=gen_uuid)
    merchant_id = Column(String, ForeignKey("merchants.id"), nullable=False)
    total_amount = Column(Float, nullable=False)
    fee_amount = Column(Float, nullable=False)
    net_amount = Column(Float, nullable=False)
    payment_count = Column(Integer, nullable=False)
    refund_count = Column(Integer, default=0)
    period_start = Column(DateTime, nullable=False)
    period_end = Column(DateTime, nullable=False)
    status = Column(String(20), default="pending")
    created_at = Column(DateTime, default=utcnow)

    merchant = relationship("Merchant", back_populates="settlements")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(String, primary_key=True, default=gen_uuid)
    entity_type = Column(String(50), nullable=False)
    entity_id = Column(String, nullable=False)
    action = Column(String(50), nullable=False)
    details = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow)
