from contextlib import asynccontextmanager
from importlib.metadata import version, PackageNotFoundError
from pathlib import Path
import tomllib

from fastapi import FastAPI

from app.database import init_db
from app.routers import merchants, payments, webhooks, reports


def _resolve_version() -> str:
    try:
        return version("payment-service")
    except PackageNotFoundError:
        pass

    try:
        with open(Path(__file__).parent.parent / "pyproject.toml", "rb") as _f:
            return tomllib.load(_f)["project"]["version"]
    except (FileNotFoundError, OSError, tomllib.TOMLDecodeError, KeyError, TypeError):
        # Health/root endpoints should remain available even outside a packaged checkout.
        return "unknown"


__version__ = _resolve_version()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="Payment Processing Service",
    description="A payment processing API with merchant management, webhooks, and reporting",
    version=__version__,
    lifespan=lifespan,
)

app.include_router(merchants.router)
app.include_router(payments.router)
app.include_router(webhooks.router)
app.include_router(reports.router)


@app.get("/health")
async def health_check():
    return {"status": "healthy", "version": __version__}


@app.get("/")
async def root():
    return {
        "service": "payment-processing",
        "version": __version__,
        "docs": "/docs",
    }
