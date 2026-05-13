from contextlib import asynccontextmanager
from importlib.metadata import PackageNotFoundError, version

from fastapi import FastAPI

from app.database import init_db
from app.routers import merchants, payments, reports, webhooks


def get_app_version() -> str:
    try:
        return version("payment-service")
    except PackageNotFoundError:
        return "unknown"


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="Payment Processing Service",
    description="A payment processing API with merchant management, webhooks, and reporting",
    version=get_app_version(),
    lifespan=lifespan,
)

app.include_router(merchants.router)
app.include_router(payments.router)
app.include_router(webhooks.router)
app.include_router(reports.router)


@app.get("/version")
async def get_version():
    return {"version": get_app_version()}


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


@app.get("/")
async def root():
    return {
        "service": "payment-processing",
        "version": get_app_version(),
        "docs": "/docs",
    }
