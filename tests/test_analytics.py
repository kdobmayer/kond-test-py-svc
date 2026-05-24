import pytest
import uuid
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_daily_with_captured_payment(client: AsyncClient, captured_payment, merchant):
    response = await client.get(f"/analytics/daily/{merchant['id']}?days=30")
    assert response.status_code == 200
    data = response.json()
    assert data["merchant_id"] == merchant["id"]
    assert data["currency"] == "USD"
    assert len(data["days"]) == 1
    day = data["days"][0]
    assert day["count"] == 1
    assert day["volume"] == 100.0
    assert day["success_rate"] == 1.0
    assert day["refund_rate"] == 0.0


@pytest.mark.asyncio
async def test_summary_with_captured_payment(client: AsyncClient, captured_payment, merchant):
    response = await client.get(f"/analytics/summary/{merchant['id']}?days=30")
    assert response.status_code == 200
    data = response.json()
    assert data["total_count"] == 1
    assert data["captured_amount"] == 100.0
    assert data["currency"] == "USD"


@pytest.mark.asyncio
async def test_trends_happy_path(client: AsyncClient, captured_payment, merchant):
    response = await client.get(f"/analytics/trends/{merchant['id']}?days=30")
    assert response.status_code == 200
    data = response.json()
    assert data["current"]["total_count"] == 1
    assert data["previous"]["total_count"] == 0
    changes = data["changes"]
    assert set(changes.keys()) == {"count", "volume", "average", "success_rate"}
    assert changes["count"]["absolute"] == 1
    assert changes["volume"]["absolute"] == 100.0
    for key in changes:
        assert changes[key]["percentage"] is None


@pytest.mark.asyncio
async def test_refund_updates_refund_rate(client: AsyncClient, captured_payment, merchant):
    pre = await client.get(f"/analytics/summary/{merchant['id']}?days=30")
    assert pre.status_code == 200
    assert pre.json()["refund_rate"] == 0.0

    refund = await client.post(
        f"/payments/{captured_payment['id']}/refund",
        json={"amount": 20.0},
    )
    assert refund.status_code == 201

    post = await client.get(f"/analytics/summary/{merchant['id']}?days=30")
    assert post.status_code == 200
    post_data = post.json()
    assert post_data["refund_rate"] > 0.0
    assert post_data["refunded_amount"] == 20.0


# --- Edge-case tests ---

UNKNOWN_ID = str(uuid.uuid4())


@pytest.mark.asyncio
async def test_404_unknown_merchant_daily(client: AsyncClient):
    response = await client.get(f"/analytics/daily/{UNKNOWN_ID}?days=30")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_404_unknown_merchant_summary(client: AsyncClient):
    response = await client.get(f"/analytics/summary/{UNKNOWN_ID}?days=30")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_404_unknown_merchant_trends(client: AsyncClient):
    response = await client.get(f"/analytics/trends/{UNKNOWN_ID}?days=30")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_empty_period_daily(client: AsyncClient, merchant):
    response = await client.get(f"/analytics/daily/{merchant['id']}?days=30")
    assert response.status_code == 200
    assert response.json()["days"] == []


@pytest.mark.asyncio
async def test_empty_period_summary(client: AsyncClient, merchant):
    response = await client.get(f"/analytics/summary/{merchant['id']}?days=30")
    assert response.status_code == 200
    data = response.json()
    assert data["total_count"] == 0
    assert data["total_volume"] == 0.0
    assert data["captured_amount"] == 0.0
    assert data["refunded_amount"] == 0.0
    assert data["average_payment"] == 0.0
    assert data["success_rate"] == 0.0
    assert data["refund_rate"] == 0.0
    assert data["unique_customers"] == 0


@pytest.mark.asyncio
async def test_empty_period_trends(client: AsyncClient, merchant):
    response = await client.get(f"/analytics/trends/{merchant['id']}?days=30")
    assert response.status_code == 200
    data = response.json()
    assert data["current"]["total_count"] == 0
    assert data["previous"]["total_count"] == 0
    for key in ("count", "volume", "average", "success_rate"):
        assert data["changes"][key]["percentage"] is None


@pytest.mark.asyncio
async def test_first_ever_data_changes_percentage_null(client: AsyncClient, captured_payment, merchant):
    response = await client.get(f"/analytics/trends/{merchant['id']}?days=30")
    assert response.status_code == 200
    data = response.json()
    changes = data["changes"]
    assert changes["count"]["absolute"] == 1
    assert changes["volume"]["absolute"] == 100.0
    assert changes["success_rate"]["absolute"] > 0.0
    for key in ("count", "volume", "average", "success_rate"):
        assert changes[key]["percentage"] is None


@pytest.mark.asyncio
async def test_voided_payment_success_rate_zero(client: AsyncClient, merchant):
    pay = await client.post("/payments", json={
        "merchant_id": merchant["id"],
        "amount": 100.00,
        "currency": "USD",
        "description": "Test void payment",
    })
    assert pay.status_code == 201
    payment_id = pay.json()["id"]

    void = await client.post(f"/payments/{payment_id}/void")
    assert void.status_code == 200

    response = await client.get(f"/analytics/summary/{merchant['id']}?days=30")
    assert response.status_code == 200
    data = response.json()
    assert data["total_count"] == 1
    assert data["success_rate"] == 0.0


@pytest.mark.asyncio
async def test_days_param_zero_returns_422(client: AsyncClient, merchant):
    response = await client.get(f"/analytics/daily/{merchant['id']}?days=0")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_days_param_400_returns_422(client: AsyncClient, merchant):
    response = await client.get(f"/analytics/daily/{merchant['id']}?days=400")
    assert response.status_code == 422
