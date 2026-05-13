import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_status_code(client: AsyncClient):
    response = await client.get("/health")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_health_response_body(client: AsyncClient):
    response = await client.get("/health")
    data = response.json()
    assert data["status"] == "healthy"
    assert data["version"] == "0.1.0"
