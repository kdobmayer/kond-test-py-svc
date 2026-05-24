import pytest
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
