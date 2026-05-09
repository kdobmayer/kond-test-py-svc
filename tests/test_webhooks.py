import pytest
from httpx import AsyncClient

from app.services.webhooks import verify_signature, compute_signature


@pytest.mark.asyncio
async def test_create_webhook_endpoint(client: AsyncClient, merchant):
    response = await client.post("/webhooks/endpoints", json={
        "merchant_id": merchant["id"],
        "url": "https://example.com/webhook",
        "events": ["payment.created", "payment.captured"],
    })
    assert response.status_code == 201
    data = response.json()
    assert data["url"] == "https://example.com/webhook"
    assert data["events"] == ["payment.created", "payment.captured"]
    assert data["is_active"] is True


@pytest.mark.asyncio
async def test_create_webhook_invalid_merchant(client: AsyncClient):
    response = await client.post("/webhooks/endpoints", json={
        "merchant_id": "nonexistent",
        "url": "https://example.com/webhook",
        "events": ["payment.created"],
    })
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_webhook_invalid_url(client: AsyncClient, merchant):
    response = await client.post("/webhooks/endpoints", json={
        "merchant_id": merchant["id"],
        "url": "not-a-url",
        "events": ["payment.created"],
    })
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_webhook_invalid_event(client: AsyncClient, merchant):
    response = await client.post("/webhooks/endpoints", json={
        "merchant_id": merchant["id"],
        "url": "https://example.com/webhook",
        "events": ["invalid.event"],
    })
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_webhook_endpoints(client: AsyncClient, merchant):
    await client.post("/webhooks/endpoints", json={
        "merchant_id": merchant["id"],
        "url": "https://example.com/hook1",
        "events": ["payment.created"],
    })
    response = await client.get(f"/webhooks/endpoints?merchant_id={merchant['id']}")
    assert response.status_code == 200
    assert len(response.json()) >= 1


@pytest.mark.asyncio
async def test_get_webhook_endpoint(client: AsyncClient, merchant):
    create_response = await client.post("/webhooks/endpoints", json={
        "merchant_id": merchant["id"],
        "url": "https://example.com/hook",
        "events": ["payment.created"],
    })
    endpoint_id = create_response.json()["id"]

    response = await client.get(f"/webhooks/endpoints/{endpoint_id}")
    assert response.status_code == 200
    assert response.json()["id"] == endpoint_id


@pytest.mark.asyncio
async def test_update_webhook_endpoint(client: AsyncClient, merchant):
    create_response = await client.post("/webhooks/endpoints", json={
        "merchant_id": merchant["id"],
        "url": "https://example.com/hook",
        "events": ["payment.created"],
    })
    endpoint_id = create_response.json()["id"]

    response = await client.patch(f"/webhooks/endpoints/{endpoint_id}", json={
        "url": "https://example.com/new-hook",
        "is_active": False,
    })
    assert response.status_code == 200
    assert response.json()["url"] == "https://example.com/new-hook"
    assert response.json()["is_active"] is False


@pytest.mark.asyncio
async def test_delete_webhook_endpoint(client: AsyncClient, merchant):
    create_response = await client.post("/webhooks/endpoints", json={
        "merchant_id": merchant["id"],
        "url": "https://example.com/hook",
        "events": ["payment.created"],
    })
    endpoint_id = create_response.json()["id"]

    response = await client.delete(f"/webhooks/endpoints/{endpoint_id}")
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_verify_signature_valid(client: AsyncClient):
    payload = '{"event": "test"}'
    secret = "test-secret"
    sig = compute_signature(payload, secret)

    response = await client.post("/webhooks/verify", json={
        "payload": payload,
        "signature": sig,
        "secret": secret,
    })
    assert response.status_code == 200
    assert response.json()["valid"] is True


@pytest.mark.asyncio
async def test_verify_signature_invalid(client: AsyncClient):
    response = await client.post("/webhooks/verify", json={
        "payload": '{"event": "test"}',
        "signature": "invalid-signature",
        "secret": "test-secret",
    })
    assert response.status_code == 200
    assert response.json()["valid"] is False


def test_compute_and_verify_signature():
    payload = '{"amount": 100}'
    secret = "my-webhook-secret"
    signature = compute_signature(payload, secret)
    assert verify_signature(payload, signature, secret)
    assert not verify_signature(payload, "wrong", secret)
    assert not verify_signature("tampered", signature, secret)
