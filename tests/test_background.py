import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, AsyncMock

from app.models import (
    Merchant, Payment, PaymentStatus, WebhookDelivery, DeliveryStatus,
    WebhookEndpoint,
)
from app.database import Base

from tests.conftest import TestSessionLocal, engine


@pytest.fixture(autouse=True)
def patch_async_session():
    """Patch the async_session used by background services to use test DB."""
    with patch("app.services.background.async_session", TestSessionLocal):
        with patch("app.services.webhooks.async_session", TestSessionLocal):
            yield


@pytest.mark.asyncio
async def test_reconcile_merchant_balances():
    """Test that balance reconciliation corrects drift."""
    from app.services.background import reconcile_merchant_balances

    async with TestSessionLocal() as db:
        merchant = Merchant(
            name="Reconcile Test",
            email="reconcile@test.com",
            api_key="pk_test_reconcile",
            api_secret="sk_test_reconcile",
            balance=999.99,  # Intentionally wrong
            currency="USD",
        )
        db.add(merchant)
        await db.flush()

        # Add a captured payment
        payment = Payment(
            merchant_id=merchant.id,
            amount=100.00,
            captured_amount=100.00,
            refunded_amount=25.00,
            status=PaymentStatus.PARTIALLY_REFUNDED,
            currency="USD",
        )
        db.add(payment)
        await db.commit()

        merchant_id = merchant.id

    # Run reconciliation
    await reconcile_merchant_balances()

    # Check balance was corrected
    async with TestSessionLocal() as db:
        from sqlalchemy import select
        result = await db.execute(
            select(Merchant).where(Merchant.id == merchant_id)
        )
        merchant = result.scalar_one()
        # Expected: 100 captured - 25 refunded = 75
        assert merchant.balance == 75.0


@pytest.mark.asyncio
async def test_cleanup_old_deliveries():
    """Test that old deliveries are cleaned up."""
    from app.services.background import cleanup_old_deliveries
    import json

    async with TestSessionLocal() as db:
        merchant = Merchant(
            name="Cleanup Test",
            email="cleanup@test.com",
            api_key="pk_test_cleanup",
            api_secret="sk_test_cleanup",
            balance=0.0,
            currency="USD",
        )
        db.add(merchant)
        await db.flush()

        endpoint = WebhookEndpoint(
            merchant_id=merchant.id,
            url="https://example.com/hook",
            secret="test-secret",
            events=json.dumps(["payment.created"]),
        )
        db.add(endpoint)
        await db.flush()

        # Add an old delivery
        old_delivery = WebhookDelivery(
            endpoint_id=endpoint.id,
            event_type="payment.created",
            payload='{"test": true}',
            status=DeliveryStatus.DELIVERED,
            created_at=datetime.now(timezone.utc) - timedelta(days=60),
        )
        db.add(old_delivery)
        await db.commit()

    deleted = await cleanup_old_deliveries(retention_days=30)
    assert deleted >= 1


@pytest.mark.asyncio
@patch("app.services.background.dispatch_webhook_event", new_callable=AsyncMock)
async def test_calculate_daily_settlements(mock_dispatch):
    """Test daily settlement calculation."""
    from app.services.background import calculate_daily_settlements

    async with TestSessionLocal() as db:
        merchant = Merchant(
            name="Settlement Test",
            email="settlement@test.com",
            api_key="pk_test_settlement",
            api_secret="sk_test_settlement",
            balance=200.0,
            currency="USD",
            is_active=True,
        )
        db.add(merchant)
        await db.flush()

        # Add a captured payment from yesterday
        yesterday = datetime.now(timezone.utc) - timedelta(hours=12)
        payment = Payment(
            merchant_id=merchant.id,
            amount=200.00,
            captured_amount=200.00,
            refunded_amount=0.0,
            status=PaymentStatus.CAPTURED,
            currency="USD",
            created_at=yesterday,
        )
        db.add(payment)
        await db.commit()

    await calculate_daily_settlements(fee_rate=0.029)
    # Validates the function runs without error
