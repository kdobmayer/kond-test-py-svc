from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import init_db, get_db
from app.models import Payment, Merchant, WebhookDelivery, DeliveryStatus
from app.routers import merchants, payments, webhooks, reports
from app.schemas import MetricsResponse


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="Payment Processing Service",
    description="A payment processing API with merchant management, webhooks, and reporting",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(merchants.router)
app.include_router(payments.router)
app.include_router(webhooks.router)
app.include_router(reports.router)


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


@app.get("/metrics", response_model=MetricsResponse)
async def get_metrics(db: AsyncSession = Depends(get_db)) -> MetricsResponse:
    total_payments = (await db.execute(select(func.count(Payment.id)))).scalar_one()
    total_merchants = (await db.execute(select(func.count(Merchant.id)))).scalar_one()
    total_webhooks_delivered = (await db.execute(
        select(func.count(WebhookDelivery.id)).where(
            WebhookDelivery.status == DeliveryStatus.DELIVERED
        )
    )).scalar_one()
    return MetricsResponse(
        total_payments=total_payments,
        total_merchants=total_merchants,
        total_webhooks_delivered=total_webhooks_delivered,
    )


@app.get("/")
async def root():
    return {
        "service": "payment-processing",
        "version": "0.1.0",
        "docs": "/docs",
    }
