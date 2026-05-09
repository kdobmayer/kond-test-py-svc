import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_merchant(client: AsyncClient):
    response = await client.post("/merchants", json={
        "name": "Acme Corp",
        "email": "billing@acme.com",
        "currency": "USD",
    })
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Acme Corp"
    assert data["email"] == "billing@acme.com"
    assert data["api_key"].startswith("pk_")
    assert data["balance"] == 0.0
    assert data["is_active"] is True


@pytest.mark.asyncio
async def test_create_merchant_duplicate_email(client: AsyncClient, merchant):
    response = await client.post("/merchants", json={
        "name": "Another Merchant",
        "email": "test@merchant.com",
        "currency": "USD",
    })
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_create_merchant_invalid_email(client: AsyncClient):
    response = await client.post("/merchants", json={
        "name": "Bad Email",
        "email": "not-an-email",
        "currency": "USD",
    })
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_merchants(client: AsyncClient, merchant):
    response = await client.get("/merchants")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert len(data["merchants"]) >= 1


@pytest.mark.asyncio
async def test_list_merchants_filter_active(client: AsyncClient, merchant):
    response = await client.get("/merchants?is_active=true")
    assert response.status_code == 200
    data = response.json()
    assert all(m["is_active"] for m in data["merchants"])


@pytest.mark.asyncio
async def test_get_merchant(client: AsyncClient, merchant):
    response = await client.get(f"/merchants/{merchant['id']}")
    assert response.status_code == 200
    assert response.json()["id"] == merchant["id"]


@pytest.mark.asyncio
async def test_get_merchant_not_found(client: AsyncClient):
    response = await client.get("/merchants/nonexistent")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_merchant(client: AsyncClient, merchant):
    response = await client.patch(f"/merchants/{merchant['id']}", json={
        "name": "Updated Name",
    })
    assert response.status_code == 200
    assert response.json()["name"] == "Updated Name"


@pytest.mark.asyncio
async def test_delete_merchant(client: AsyncClient, merchant):
    response = await client.delete(f"/merchants/{merchant['id']}")
    assert response.status_code == 204

    response = await client.get(f"/merchants/{merchant['id']}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_rotate_api_key(client: AsyncClient, merchant):
    old_key = merchant["api_key"]
    response = await client.post(f"/merchants/{merchant['id']}/rotate-key")
    assert response.status_code == 200
    assert response.json()["api_key"] != old_key


@pytest.mark.asyncio
async def test_get_merchant_balance(client: AsyncClient, merchant):
    response = await client.get(f"/merchants/{merchant['id']}/balance")
    assert response.status_code == 200
    data = response.json()
    assert data["balance"] == 0.0
    assert data["currency"] == "USD"
