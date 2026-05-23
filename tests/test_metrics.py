import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_metrics_empty_db(client: AsyncClient):
    response = await client.get("/metrics")
    assert response.status_code == 200
    data = response.json()
    assert data["total_payments"] == 0
    assert data["total_merchants"] == 0
    assert data["total_webhooks_delivered"] == 0


@pytest.mark.asyncio
async def test_metrics_with_data(client: AsyncClient, captured_payment):
    response = await client.get("/metrics")
    assert response.status_code == 200
    data = response.json()
    assert data["total_payments"] >= 1
    assert data["total_merchants"] >= 1
    assert data["total_webhooks_delivered"] >= 0
