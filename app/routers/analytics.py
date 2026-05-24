from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Merchant, Payment
from app.schemas import (
    AnalyticsDailyResponse,
    AnalyticsDailyPoint,
    AnalyticsSummary,
    AnalyticsChange,
    AnalyticsTrendsResponse,
)
from app.services.analytics import aggregate_daily, summarize, compare_periods

router = APIRouter(prefix="/analytics", tags=["analytics"])


async def _get_merchant_or_404(merchant_id: str, db: AsyncSession) -> Merchant:
    result = await db.execute(select(Merchant).where(Merchant.id == merchant_id))
    merchant = result.scalar_one_or_none()
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")
    return merchant


async def _fetch_payments(
    merchant_id: str,
    period_start: datetime,
    period_end: datetime,
    db: AsyncSession,
    end_exclusive: bool = False,
) -> list[Payment]:
    end_cond = Payment.created_at < period_end if end_exclusive else Payment.created_at <= period_end
    result = await db.execute(
        select(Payment).where(
            and_(
                Payment.merchant_id == merchant_id,
                Payment.created_at >= period_start,
                end_cond,
            )
        )
    )
    return result.scalars().all()


@router.get("/daily/{merchant_id}", response_model=AnalyticsDailyResponse)
async def get_analytics_daily(
    merchant_id: str,
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
):
    merchant = await _get_merchant_or_404(merchant_id, db)
    period_end = datetime.now(timezone.utc)
    period_start = period_end - timedelta(days=days)
    payments = await _fetch_payments(merchant_id, period_start, period_end, db)
    daily_points = [AnalyticsDailyPoint(**point) for point in aggregate_daily(payments)]
    return AnalyticsDailyResponse(
        merchant_id=merchant_id,
        period_start=period_start,
        period_end=period_end,
        currency=merchant.currency,
        days=daily_points,
    )


@router.get("/summary/{merchant_id}", response_model=AnalyticsSummary)
async def get_analytics_summary(
    merchant_id: str,
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
):
    merchant = await _get_merchant_or_404(merchant_id, db)
    period_end = datetime.now(timezone.utc)
    period_start = period_end - timedelta(days=days)
    payments = await _fetch_payments(merchant_id, period_start, period_end, db)
    stats = summarize(payments)
    return AnalyticsSummary(
        merchant_id=merchant_id,
        period_start=period_start,
        period_end=period_end,
        currency=merchant.currency,
        **stats,
    )


@router.get("/trends/{merchant_id}", response_model=AnalyticsTrendsResponse)
async def get_analytics_trends(
    merchant_id: str,
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
):
    merchant = await _get_merchant_or_404(merchant_id, db)
    period_end = datetime.now(timezone.utc)
    period_start = period_end - timedelta(days=days)
    previous_start = period_start - timedelta(days=days)

    current_payments = await _fetch_payments(merchant_id, period_start, period_end, db)
    previous_payments = await _fetch_payments(merchant_id, previous_start, period_start, db, end_exclusive=True)

    current_stats = summarize(current_payments)
    previous_stats = summarize(previous_payments)
    changes_raw = compare_periods(current_payments, previous_payments)

    return AnalyticsTrendsResponse(
        merchant_id=merchant_id,
        current=AnalyticsSummary(
            merchant_id=merchant_id,
            period_start=period_start,
            period_end=period_end,
            currency=merchant.currency,
            **current_stats,
        ),
        previous=AnalyticsSummary(
            merchant_id=merchant_id,
            period_start=previous_start,
            period_end=period_start,
            currency=merchant.currency,
            **previous_stats,
        ),
        changes={k: AnalyticsChange(**v) for k, v in changes_raw.items()},
    )
