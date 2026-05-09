"""Background task functions for webhook delivery and settlement calculation."""

import json
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models import (
    Payment, PaymentStatus, Merchant, Settlement,
    WebhookEndpoint, WebhookDelivery, DeliveryStatus, Refund,
)
from app.services.webhooks import dispatch_webhook_event


async def process_pending_deliveries():
    """Process all pending webhook deliveries.

    Finds deliveries that are still pending and attempts redelivery.
    Called periodically by a scheduler.
    """
    async with async_session() as db:
        result = await db.execute(
            select(WebhookDelivery).where(
                WebhookDelivery.status == DeliveryStatus.PENDING,
                WebhookDelivery.attempts < 3,
            )
        )
        pending = result.scalars().all()

        for delivery in pending:
            endpoint_result = await db.execute(
                select(WebhookEndpoint).where(
                    WebhookEndpoint.id == delivery.endpoint_id
                )
            )
            endpoint = endpoint_result.scalar_one_or_none()
            if not endpoint or not endpoint.is_active:
                delivery.status = DeliveryStatus.FAILED
                continue

            from app.services.webhooks import _attempt_delivery
            await _attempt_delivery(db, delivery, endpoint)

        await db.commit()


async def calculate_daily_settlements(fee_rate: float = 0.029):
    """Calculate settlements for all active merchants.

    Aggregates yesterday's captured payments and creates settlement records.
    Cross-module flow: settlement aggregates payments.
    """
    async with async_session() as db:
        # Get all active merchants
        merchants_result = await db.execute(
            select(Merchant).where(Merchant.is_active == True)
        )
        merchants = merchants_result.scalars().all()

        period_end = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        period_start = period_end - timedelta(days=1)

        for merchant in merchants:
            # Get captured payments for the period
            payments_result = await db.execute(
                select(Payment).where(
                    and_(
                        Payment.merchant_id == merchant.id,
                        Payment.status.in_([
                            PaymentStatus.CAPTURED,
                            PaymentStatus.REFUNDED,
                            PaymentStatus.PARTIALLY_REFUNDED,
                        ]),
                        Payment.created_at >= period_start,
                        Payment.created_at < period_end,
                    )
                )
            )
            payments = payments_result.scalars().all()

            if not payments:
                continue

            total_amount = sum(p.captured_amount for p in payments)
            total_refunds = sum(p.refunded_amount for p in payments)
            net_captured = total_amount - total_refunds

            if net_captured <= 0:
                continue

            fee_amount = round(net_captured * fee_rate, 2)
            net_amount = round(net_captured - fee_amount, 2)

            # Count refunds
            refund_count = 0
            for payment in payments:
                refunds_result = await db.execute(
                    select(func.count(Refund.id)).where(
                        Refund.payment_id == payment.id
                    )
                )
                refund_count += refunds_result.scalar()

            settlement = Settlement(
                merchant_id=merchant.id,
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

            # Dispatch webhook for settlement
            await dispatch_webhook_event(
                merchant_id=merchant.id,
                event_type="settlement.completed",
                payload={
                    "settlement_id": settlement.id,
                    "net_amount": net_amount,
                    "period_start": period_start.isoformat(),
                    "period_end": period_end.isoformat(),
                },
            )

        await db.commit()


async def cleanup_old_deliveries(retention_days: int = 30):
    """Remove webhook deliveries older than retention period."""
    async with async_session() as db:
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        result = await db.execute(
            select(WebhookDelivery).where(
                WebhookDelivery.created_at < cutoff,
                WebhookDelivery.status.in_([
                    DeliveryStatus.DELIVERED,
                    DeliveryStatus.FAILED,
                ]),
            )
        )
        old_deliveries = result.scalars().all()
        for delivery in old_deliveries:
            await db.delete(delivery)
        await db.commit()
        return len(old_deliveries)


async def reconcile_merchant_balances():
    """Reconcile merchant balances against actual payment records.

    Recalculates balance from captured payments minus refunds.
    """
    async with async_session() as db:
        merchants_result = await db.execute(select(Merchant))
        merchants = merchants_result.scalars().all()

        for merchant in merchants:
            # Sum captured amounts
            captured_result = await db.execute(
                select(func.coalesce(func.sum(Payment.captured_amount), 0.0)).where(
                    and_(
                        Payment.merchant_id == merchant.id,
                        Payment.status.in_([
                            PaymentStatus.CAPTURED,
                            PaymentStatus.REFUNDED,
                            PaymentStatus.PARTIALLY_REFUNDED,
                        ]),
                    )
                )
            )
            total_captured = captured_result.scalar()

            # Sum refunded amounts
            refunded_result = await db.execute(
                select(func.coalesce(func.sum(Payment.refunded_amount), 0.0)).where(
                    Payment.merchant_id == merchant.id,
                )
            )
            total_refunded = refunded_result.scalar()

            expected_balance = total_captured - total_refunded
            if abs(merchant.balance - expected_balance) > 0.01:
                merchant.balance = expected_balance

        await db.commit()
