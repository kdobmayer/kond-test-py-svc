from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Dispute, DisputeStatus, Merchant, Payment, PaymentStatus, Refund, AuditLog
from app.schemas import DisputeListResponse, DisputeResolve, DisputeResponse
from app.services.webhooks import dispatch_webhook_event

router = APIRouter(prefix="/disputes", tags=["disputes"])


@router.get("", response_model=DisputeListResponse)
async def list_disputes(
    status: str | None = None,
    merchant_id: str | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> DisputeListResponse:
    query = select(Dispute)
    count_query = select(func.count(Dispute.id))

    if status:
        try:
            dispute_status = DisputeStatus(status)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid dispute status") from exc
        query = query.where(Dispute.status == dispute_status)
        count_query = count_query.where(Dispute.status == dispute_status)
    if merchant_id:
        query = query.where(Dispute.merchant_id == merchant_id)
        count_query = count_query.where(Dispute.merchant_id == merchant_id)

    total_result = await db.execute(count_query)
    total = total_result.scalar()

    result = await db.execute(
        query.order_by(Dispute.created_at.desc()).offset(skip).limit(limit)
    )
    disputes = result.scalars().all()

    return DisputeListResponse(disputes=disputes, total=total)


@router.patch("/{dispute_id}/resolve", response_model=DisputeResponse)
async def resolve_dispute(
    dispute_id: str,
    data: DisputeResolve,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> DisputeResponse:
    result = await db.execute(select(Dispute).where(Dispute.id == dispute_id))
    dispute = result.scalar_one_or_none()
    if not dispute:
        raise HTTPException(status_code=404, detail="Dispute not found")

    if dispute.status not in (DisputeStatus.OPEN, DisputeStatus.UNDER_REVIEW):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot resolve dispute in status '{dispute.status.value}'"
        )

    if data.resolution == DisputeStatus.ACCEPTED:
        payment_result = await db.execute(
            select(Payment).where(Payment.id == dispute.payment_id)
        )
        payment = payment_result.scalar_one()

        available = round(payment.captured_amount - payment.refunded_amount, 2)
        if dispute.amount > available:
            raise HTTPException(
                status_code=400,
                detail=f"Dispute amount {dispute.amount} exceeds available {available}"
            )

        refund = Refund(
            payment_id=payment.id,
            amount=dispute.amount,
            reason=f"Dispute accepted: {dispute.reason}",
        )
        db.add(refund)
        await db.flush()

        payment.refunded_amount = round(payment.refunded_amount + dispute.amount, 2)
        if payment.refunded_amount >= payment.captured_amount:
            payment.status = PaymentStatus.REFUNDED
        else:
            payment.status = PaymentStatus.PARTIALLY_REFUNDED

        merchant_result = await db.execute(
            select(Merchant).where(Merchant.id == dispute.merchant_id)
        )
        merchant = merchant_result.scalar_one_or_none()
        if merchant:
            merchant.balance -= dispute.amount

        dispute.refund_id = refund.id
        dispute.status = DisputeStatus.ACCEPTED

        background_tasks.add_task(
            dispatch_webhook_event,
            merchant_id=dispute.merchant_id,
            event_type="payment.refunded",
            payload={
                "payment_id": payment.id,
                "refund_id": refund.id,
                "amount": dispute.amount,
                "reason": "dispute_accepted",
            },
        )
    else:
        dispute.status = DisputeStatus.REJECTED

    dispute.resolution_note = data.resolution_note

    audit = AuditLog(
        entity_type="dispute",
        entity_id=dispute.id,
        action=f"resolved_{data.resolution.value}",
        details=f"Dispute {data.resolution.value}. Note: {data.resolution_note}",
    )
    db.add(audit)
    await db.flush()

    return dispute
