from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Payment, PaymentStatus, Merchant, Settlement, Refund
from app.schemas import TransactionSummary, SettlementReport, SettlementListResponse

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/transactions/{merchant_id}", response_model=TransactionSummary)
async def get_transaction_summary(
    merchant_id: str,
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
):
    """Get transaction summary for a merchant over a period."""
    merchant_result = await db.execute(
        select(Merchant).where(Merchant.id == merchant_id)
    )
    merchant = merchant_result.scalar_one_or_none()
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")

    period_end = datetime.now(timezone.utc)
    period_start = period_end - timedelta(days=days)

    # Get payment stats
    payments_query = select(Payment).where(
        and_(
            Payment.merchant_id == merchant_id,
            Payment.created_at >= period_start,
            Payment.created_at <= period_end,
        )
    )
    result = await db.execute(payments_query)
    payments = result.scalars().all()

    total_payments = len(payments)
    total_amount = sum(p.amount for p in payments)
    captured_amount = sum(p.captured_amount for p in payments)
    refunded_amount = sum(p.refunded_amount for p in payments)
    voided_count = sum(1 for p in payments if p.status == PaymentStatus.VOIDED)
    average_payment = total_amount / total_payments if total_payments > 0 else 0.0

    return TransactionSummary(
        merchant_id=merchant_id,
        period_start=period_start,
        period_end=period_end,
        total_payments=total_payments,
        total_amount=round(total_amount, 2),
        captured_amount=round(captured_amount, 2),
        refunded_amount=round(refunded_amount, 2),
        voided_count=voided_count,
        average_payment=round(average_payment, 2),
        currency=merchant.currency,
    )


@router.get("/settlements/{merchant_id}", response_model=SettlementListResponse)
async def list_settlements(
    merchant_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """List settlements for a merchant."""
    merchant_result = await db.execute(
        select(Merchant).where(Merchant.id == merchant_id)
    )
    if not merchant_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Merchant not found")

    count_result = await db.execute(
        select(func.count(Settlement.id)).where(Settlement.merchant_id == merchant_id)
    )
    total = count_result.scalar()

    result = await db.execute(
        select(Settlement)
        .where(Settlement.merchant_id == merchant_id)
        .order_by(Settlement.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    settlements = result.scalars().all()

    return SettlementListResponse(settlements=settlements, total=total)


@router.post("/settlements/{merchant_id}/calculate", response_model=SettlementReport)
async def calculate_settlement(
    merchant_id: str,
    days: int = Query(7, ge=1, le=90),
    fee_rate: float = Query(0.029, ge=0.0, le=0.1),
    db: AsyncSession = Depends(get_db),
):
    """Calculate and create a settlement for a merchant.

    Cross-module flow: settlement aggregates payments.
    """
    merchant_result = await db.execute(
        select(Merchant).where(Merchant.id == merchant_id)
    )
    merchant = merchant_result.scalar_one_or_none()
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")

    period_end = datetime.now(timezone.utc)
    period_start = period_end - timedelta(days=days)

    # Get captured payments in period
    payments_result = await db.execute(
        select(Payment).where(
            and_(
                Payment.merchant_id == merchant_id,
                Payment.status.in_([
                    PaymentStatus.CAPTURED,
                    PaymentStatus.REFUNDED,
                    PaymentStatus.PARTIALLY_REFUNDED,
                ]),
                Payment.created_at >= period_start,
                Payment.created_at <= period_end,
            )
        )
    )
    payments = payments_result.scalars().all()

    if not payments:
        raise HTTPException(status_code=400, detail="No payments found for settlement period")

    total_amount = sum(p.captured_amount for p in payments)
    total_refunds = sum(p.refunded_amount for p in payments)
    net_captured = total_amount - total_refunds
    fee_amount = round(net_captured * fee_rate, 2)
    net_amount = round(net_captured - fee_amount, 2)

    # Count refunds
    refund_count = 0
    for payment in payments:
        refunds_result = await db.execute(
            select(func.count(Refund.id)).where(Refund.payment_id == payment.id)
        )
        refund_count += refunds_result.scalar()

    settlement = Settlement(
        merchant_id=merchant_id,
        total_amount=round(total_amount, 2),
        fee_amount=fee_amount,
        net_amount=net_amount,
        payment_count=len(payments),
        refund_count=refund_count,
        period_start=period_start,
        period_end=period_end,
        status="completed",
    )
    db.add(settlement)
    await db.flush()

    return settlement


@router.get("/daily/{merchant_id}")
async def get_daily_breakdown(
    merchant_id: str,
    days: int = Query(7, ge=1, le=30),
    db: AsyncSession = Depends(get_db),
):
    """Get daily payment breakdown for a merchant."""
    merchant_result = await db.execute(
        select(Merchant).where(Merchant.id == merchant_id)
    )
    if not merchant_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Merchant not found")

    period_end = datetime.now(timezone.utc)
    period_start = period_end - timedelta(days=days)

    result = await db.execute(
        select(Payment).where(
            and_(
                Payment.merchant_id == merchant_id,
                Payment.created_at >= period_start,
            )
        ).order_by(Payment.created_at)
    )
    payments = result.scalars().all()

    # Group by day
    daily = {}
    for payment in payments:
        day_key = payment.created_at.strftime("%Y-%m-%d")
        if day_key not in daily:
            daily[day_key] = {"date": day_key, "count": 0, "total": 0.0, "captured": 0.0}
        daily[day_key]["count"] += 1
        daily[day_key]["total"] += payment.amount
        daily[day_key]["captured"] += payment.captured_amount

    return {"merchant_id": merchant_id, "days": sorted(daily.values(), key=lambda x: x["date"])}
