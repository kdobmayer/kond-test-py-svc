import pytest
import pytest_asyncio
from unittest.mock import patch
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.database import Base, get_db
from app.main import app

TEST_DATABASE_URL = "sqlite+aiosqlite:///./test_payment_service.db"

engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def override_get_db():
    async with TestSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


app.dependency_overrides[get_db] = override_get_db


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture(autouse=True)
def patch_webhook_session():
    """Patch async_session in webhook service to use test DB."""
    with patch("app.services.webhooks.async_session", TestSessionLocal):
        yield


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def db_session():
    async with TestSessionLocal() as session:
        yield session


@pytest_asyncio.fixture
async def merchant(client: AsyncClient):
    response = await client.post("/merchants", json={
        "name": "Test Merchant",
        "email": "test@merchant.com",
        "currency": "USD",
    })
    return response.json()


@pytest_asyncio.fixture
async def payment(client: AsyncClient, merchant):
    response = await client.post("/payments", json={
        "merchant_id": merchant["id"],
        "amount": 100.00,
        "currency": "USD",
        "description": "Test payment",
    })
    return response.json()


@pytest_asyncio.fixture
async def captured_payment(client: AsyncClient, payment):
    response = await client.post(f"/payments/{payment['id']}/capture", json={})
    return response.json()
