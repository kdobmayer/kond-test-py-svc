from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.database import init_db
from app.routers import disputes, merchants, payments, webhooks, reports


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
app.include_router(disputes.router)
app.include_router(webhooks.router)
app.include_router(reports.router)


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


@app.get("/")
async def root():
    return {
        "service": "payment-processing",
        "version": "0.1.0",
        "docs": "/docs",
    }
