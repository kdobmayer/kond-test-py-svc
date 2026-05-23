import json
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Payment, PaymentStatus, Merchant, Refund, AuditLog
from app.rate_limit import check_rate_limit, require_rate_limit
from app.schemas import (
    PaymentCreate, PaymentCaptureRequest, PaymentResponse,
    PaymentListResponse, RefundCreate, RefundResponse,
)
from app.services.webhooks import dispatch_webhook_event

router = APIRouter(prefix="/payments", tags=["payments"])


@router.post("", response_model=PaymentResponse, status_code=201)
async def create_payment(
    data: PaymentCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(require_rate_limit),
):
    # Check merchant exists and is active
    merchant_result = await db.execute(
        select(Merchant).where(Merchant.id == data.merchant_id)
    )
    merchant = merchant_result.scalar_one_or_none()
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")
    if merchant.api_key != api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
    if not merchant.is_active:
        raise HTTPException(status_code=400, detail="Merchant is not active")

    allowed, retry_after = await check_rate_limit(merchant.api_key)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={"Retry-After": str(retry_after)},
        )

    # Idempotency check
    if data.idempotency_key:
        existing = await db.execute(
            select(Payment).where(Payment.idempotency_key == data.idempotency_key)
        )
        existing_payment = existing.scalar_one_or_none()
        if existing_payment:
            return existing_payment

    payment = Payment(
        merchant_id=data.merchant_id,
        amount=data.amount,
        currency=data.currency,
        status=PaymentStatus.AUTHORIZED,
        description=data.description,
        customer_email=data.customer_email,
        idempotency_key=data.idempotency_key,
        metadata_json=json.dumps(data.metadata) if data.metadata else None,
    )
    db.add(payment)
    await db.flush()

    audit = AuditLog(
        entity_type="payment",
        entity_id=payment.id,
        action="created",
        details=f"Payment of {data.amount} {data.currency} created for merchant {data.merchant_id}",
    )
    db.add(audit)
    await db.flush()

    # Cross-module flow: payment triggers webhook
    background_tasks.add_task(
        dispatch_webhook_event,
        merchant_id=data.merchant_id,
        event_type="payment.created",
        payload={"payment_id": payment.id, "amount": payment.amount, "currency": payment.currency},
    )

    return payment


@router.get("", response_model=PaymentListResponse)
async def list_payments(
    merchant_id: str | None = None,
    status: str | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    query = select(Payment)
    count_query = select(func.count(Payment.id))

    if merchant_id:
        query = query.where(Payment.merchant_id == merchant_id)
        count_query = count_query.where(Payment.merchant_id == merchant_id)
    if status:
        query = query.where(Payment.status == status)
        count_query = count_query.where(Payment.status == status)

    total_result = await db.execute(count_query)
    total = total_result.scalar()

    result = await db.execute(
        query.order_by(Payment.created_at.desc()).offset(skip).limit(limit)
    )
    payments = result.scalars().all()

    return PaymentListResponse(payments=payments, total=total)


@router.get("/{payment_id}", response_model=PaymentResponse)
async def get_payment(payment_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Payment).where(Payment.id == payment_id))
    payment = result.scalar_one_or_none()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    return payment


@router.post("/{payment_id}/capture", response_model=PaymentResponse)
async def capture_payment(
    payment_id: str,
    data: PaymentCaptureRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Payment).where(Payment.id == payment_id))
    payment = result.scalar_one_or_none()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")

    if payment.status != PaymentStatus.AUTHORIZED:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot capture payment in status '{payment.status.value}'"
        )

    capture_amount = data.amount if data.amount else payment.amount
    if capture_amount > payment.amount:
        raise HTTPException(status_code=400, detail="Capture amount exceeds payment amount")

    payment.captured_amount = capture_amount
    payment.status = PaymentStatus.CAPTURED

    # Update merchant balance
    merchant_result = await db.execute(
        select(Merchant).where(Merchant.id == payment.merchant_id)
    )
    merchant = merchant_result.scalar_one_or_none()
    if merchant:
        merchant.balance += capture_amount

    audit = AuditLog(
        entity_type="payment",
        entity_id=payment.id,
        action="captured",
        details=f"Captured {capture_amount} {payment.currency}",
    )
    db.add(audit)
    await db.flush()

    background_tasks.add_task(
        dispatch_webhook_event,
        merchant_id=payment.merchant_id,
        event_type="payment.captured",
        payload={"payment_id": payment.id, "captured_amount": capture_amount},
    )

    return payment


@router.post("/{payment_id}/void", response_model=PaymentResponse)
async def void_payment(
    payment_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Payment).where(Payment.id == payment_id))
    payment = result.scalar_one_or_none()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")

    if payment.status not in (PaymentStatus.AUTHORIZED, PaymentStatus.PENDING):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot void payment in status '{payment.status.value}'"
        )

    payment.status = PaymentStatus.VOIDED

    audit = AuditLog(
        entity_type="payment",
        entity_id=payment.id,
        action="voided",
        details=f"Payment voided",
    )
    db.add(audit)
    await db.flush()

    background_tasks.add_task(
        dispatch_webhook_event,
        merchant_id=payment.merchant_id,
        event_type="payment.voided",
        payload={"payment_id": payment.id},
    )

    return payment


@router.post("/{payment_id}/refund", response_model=RefundResponse, status_code=201)
async def refund_payment(
    payment_id: str,
    data: RefundCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Payment).where(Payment.id == payment_id))
    payment = result.scalar_one_or_none()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")

    if payment.status not in (PaymentStatus.CAPTURED, PaymentStatus.PARTIALLY_REFUNDED):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot refund payment in status '{payment.status.value}'"
        )

    # Intentional duplication: same validation logic as in schema
    if data.amount <= 0:
        raise HTTPException(status_code=400, detail="Refund amount must be positive")

    available_for_refund = payment.captured_amount - payment.refunded_amount
    if data.amount > available_for_refund:
        raise HTTPException(
            status_code=400,
            detail=f"Refund amount {data.amount} exceeds available {available_for_refund}"
        )

    refund = Refund(
        payment_id=payment.id,
        amount=data.amount,
        reason=data.reason,
    )
    db.add(refund)

    payment.refunded_amount += data.amount
    if payment.refunded_amount >= payment.captured_amount:
        payment.status = PaymentStatus.REFUNDED
    else:
        payment.status = PaymentStatus.PARTIALLY_REFUNDED

    # Cross-module flow: refund updates merchant balance
    merchant_result = await db.execute(
        select(Merchant).where(Merchant.id == payment.merchant_id)
    )
    merchant = merchant_result.scalar_one_or_none()
    if merchant:
        merchant.balance -= data.amount

    audit = AuditLog(
        entity_type="payment",
        entity_id=payment.id,
        action="refunded",
        details=f"Refunded {data.amount} {payment.currency}. Reason: {data.reason}",
    )
    db.add(audit)
    await db.flush()

    background_tasks.add_task(
        dispatch_webhook_event,
        merchant_id=payment.merchant_id,
        event_type="payment.refunded",
        payload={
            "payment_id": payment.id,
            "refund_id": refund.id,
            "amount": data.amount,
        },
    )

    return refund


@router.get("/{payment_id}/refunds", response_model=list[RefundResponse])
async def list_refunds(payment_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Payment).where(Payment.id == payment_id))
    payment = result.scalar_one_or_none()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")

    refunds_result = await db.execute(
        select(Refund).where(Refund.payment_id == payment_id).order_by(Refund.created_at.desc())
    )
    return refunds_result.scalars().all()
