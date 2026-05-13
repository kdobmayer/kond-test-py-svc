import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_request_id_header_present(client: AsyncClient):
    response = await client.get("/health")
    assert response.status_code == 200
    assert "x-request-id" in response.headers


@pytest.mark.asyncio
async def test_request_id_is_valid_uuid4(client: AsyncClient):
    response = await client.get("/health")
    value = response.headers["x-request-id"]
    parsed = uuid.UUID(value, version=4)
    assert str(parsed) == value


@pytest.mark.asyncio
async def test_request_id_unique_per_request(client: AsyncClient):
    r1 = await client.get("/health")
    r2 = await client.get("/health")
    assert r1.headers["x-request-id"] != r2.headers["x-request-id"]


@pytest.mark.asyncio
async def test_request_id_present_on_root(client: AsyncClient):
    response = await client.get("/")
    assert response.status_code == 200
    assert "x-request-id" in response.headers
