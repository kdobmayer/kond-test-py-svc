import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_transaction_summary(client: AsyncClient, captured_payment, merchant):
    response = await client.get(f"/reports/transactions/{merchant['id']}?days=30")
    assert response.status_code == 200
    data = response.json()
    assert data["merchant_id"] == merchant["id"]
    assert data["total_payments"] >= 1
    assert data["total_amount"] >= 100.00
    assert data["currency"] == "USD"


@pytest.mark.asyncio
async def test_transaction_summary_not_found(client: AsyncClient):
    response = await client.get("/reports/transactions/nonexistent?days=30")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_calculate_settlement(client: AsyncClient, captured_payment, merchant):
    response = await client.post(
        f"/reports/settlements/{merchant['id']}/calculate?days=30&fee_rate=0.029"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["merchant_id"] == merchant["id"]
    assert data["total_amount"] == 100.00
    assert data["fee_amount"] == 2.90
    assert data["net_amount"] == 97.10
    assert data["payment_count"] == 1
    assert data["status"] == "completed"


@pytest.mark.asyncio
async def test_calculate_settlement_no_payments(client: AsyncClient, merchant):
    response = await client.post(
        f"/reports/settlements/{merchant['id']}/calculate?days=1"
    )
    # No captured payments exist in the 1-day window (payment is authorized, not captured)
    # But our fixture creates a captured_payment... let's use a fresh merchant
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_list_settlements(client: AsyncClient, captured_payment, merchant):
    # Create a settlement first
    await client.post(f"/reports/settlements/{merchant['id']}/calculate?days=30")

    response = await client.get(f"/reports/settlements/{merchant['id']}")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert len(data["settlements"]) >= 1


@pytest.mark.asyncio
async def test_daily_breakdown(client: AsyncClient, payment, merchant):
    response = await client.get(f"/reports/daily/{merchant['id']}?days=7")
    assert response.status_code == 200
    data = response.json()
    assert data["merchant_id"] == merchant["id"]
    assert len(data["days"]) >= 1


@pytest.mark.asyncio
async def test_daily_breakdown_not_found(client: AsyncClient):
    response = await client.get("/reports/daily/nonexistent?days=7")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_settlement_with_refunds(client: AsyncClient, captured_payment, merchant):
    # Create a refund
    await client.post(f"/payments/{captured_payment['id']}/refund", json={
        "amount": 20.00,
    })

    response = await client.post(
        f"/reports/settlements/{merchant['id']}/calculate?days=30&fee_rate=0.029"
    )
    assert response.status_code == 200
    data = response.json()
    # Total captured is 100, refunded is 20, net captured is 80
    # Fee: 80 * 0.029 = 2.32
    # Net: 80 - 2.32 = 77.68
    assert data["total_amount"] == 100.00
    assert data["net_amount"] == 77.68
    assert data["refund_count"] == 1
