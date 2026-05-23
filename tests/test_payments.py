import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_payment(client: AsyncClient, merchant):
    response = await client.post("/payments", json={
        "merchant_id": merchant["id"],
        "amount": 50.00,
        "currency": "USD",
        "description": "Test payment",
    }, headers={"X-API-Key": merchant["api_key"]})
    assert response.status_code == 201
    data = response.json()
    assert data["amount"] == 50.00
    assert data["status"] == "authorized"
    assert data["merchant_id"] == merchant["id"]


@pytest.mark.asyncio
async def test_create_payment_invalid_merchant(client: AsyncClient):
    response = await client.post("/payments", json={
        "merchant_id": "nonexistent",
        "amount": 50.00,
        "currency": "USD",
    }, headers={"X-API-Key": "any-key"})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_payment_inactive_merchant(client: AsyncClient, merchant):
    # Deactivate merchant
    await client.patch(f"/merchants/{merchant['id']}", json={"is_active": False})

    response = await client.post("/payments", json={
        "merchant_id": merchant["id"],
        "amount": 50.00,
        "currency": "USD",
    }, headers={"X-API-Key": merchant["api_key"]})
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_create_payment_invalid_api_key(client: AsyncClient, merchant):
    response = await client.post("/payments", json={
        "merchant_id": merchant["id"],
        "amount": 50.00,
        "currency": "USD",
    }, headers={"X-API-Key": "pk_invalid"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_payment_idempotency(client: AsyncClient, merchant):
    payload = {
        "merchant_id": merchant["id"],
        "amount": 75.00,
        "currency": "USD",
        "idempotency_key": "unique-key-123",
    }
    headers = {"X-API-Key": merchant["api_key"]}
    response1 = await client.post("/payments", json=payload, headers=headers)
    response2 = await client.post("/payments", json=payload, headers=headers)

    assert response1.status_code == 201
    assert response2.status_code == 201
    assert response1.json()["id"] == response2.json()["id"]


@pytest.mark.asyncio
async def test_create_payment_invalid_amount(client: AsyncClient, merchant):
    response = await client.post("/payments", json={
        "merchant_id": merchant["id"],
        "amount": -10.00,
        "currency": "USD",
    }, headers={"X-API-Key": merchant["api_key"]})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_payment_invalid_currency(client: AsyncClient, merchant):
    response = await client.post("/payments", json={
        "merchant_id": merchant["id"],
        "amount": 50.00,
        "currency": "XYZ",
    }, headers={"X-API-Key": merchant["api_key"]})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_payments(client: AsyncClient, payment):
    response = await client.get("/payments")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1


@pytest.mark.asyncio
async def test_list_payments_by_merchant(client: AsyncClient, payment, merchant):
    response = await client.get(f"/payments?merchant_id={merchant['id']}")
    assert response.status_code == 200
    data = response.json()
    assert all(p["merchant_id"] == merchant["id"] for p in data["payments"])


@pytest.mark.asyncio
async def test_get_payment(client: AsyncClient, payment):
    response = await client.get(f"/payments/{payment['id']}")
    assert response.status_code == 200
    assert response.json()["id"] == payment["id"]


@pytest.mark.asyncio
async def test_get_payment_not_found(client: AsyncClient):
    response = await client.get("/payments/nonexistent")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_capture_payment(client: AsyncClient, payment):
    response = await client.post(f"/payments/{payment['id']}/capture", json={})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "captured"
    assert data["captured_amount"] == 100.00


@pytest.mark.asyncio
async def test_capture_payment_partial(client: AsyncClient, payment):
    response = await client.post(f"/payments/{payment['id']}/capture", json={
        "amount": 50.00,
    })
    assert response.status_code == 200
    data = response.json()
    assert data["captured_amount"] == 50.00


@pytest.mark.asyncio
async def test_capture_payment_exceeds_amount(client: AsyncClient, payment):
    response = await client.post(f"/payments/{payment['id']}/capture", json={
        "amount": 200.00,
    })
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_capture_already_captured(client: AsyncClient, captured_payment):
    response = await client.post(f"/payments/{captured_payment['id']}/capture", json={})
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_void_payment(client: AsyncClient, payment):
    response = await client.post(f"/payments/{payment['id']}/void")
    assert response.status_code == 200
    assert response.json()["status"] == "voided"


@pytest.mark.asyncio
async def test_void_captured_payment(client: AsyncClient, captured_payment):
    response = await client.post(f"/payments/{captured_payment['id']}/void")
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_refund_payment(client: AsyncClient, captured_payment):
    response = await client.post(f"/payments/{captured_payment['id']}/refund", json={
        "amount": 50.00,
        "reason": "Customer request",
    })
    assert response.status_code == 201
    data = response.json()
    assert data["amount"] == 50.00
    assert data["reason"] == "Customer request"


@pytest.mark.asyncio
async def test_refund_full_payment(client: AsyncClient, captured_payment):
    response = await client.post(f"/payments/{captured_payment['id']}/refund", json={
        "amount": 100.00,
    })
    assert response.status_code == 201

    # Check payment status
    payment_response = await client.get(f"/payments/{captured_payment['id']}")
    assert payment_response.json()["status"] == "refunded"


@pytest.mark.asyncio
async def test_refund_exceeds_available(client: AsyncClient, captured_payment):
    response = await client.post(f"/payments/{captured_payment['id']}/refund", json={
        "amount": 150.00,
    })
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_refund_uncaptured_payment(client: AsyncClient, payment):
    response = await client.post(f"/payments/{payment['id']}/refund", json={
        "amount": 50.00,
    })
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_partial_refund_updates_status(client: AsyncClient, captured_payment):
    await client.post(f"/payments/{captured_payment['id']}/refund", json={
        "amount": 30.00,
    })
    payment_response = await client.get(f"/payments/{captured_payment['id']}")
    assert payment_response.json()["status"] == "partially_refunded"


@pytest.mark.asyncio
async def test_list_refunds(client: AsyncClient, captured_payment):
    await client.post(f"/payments/{captured_payment['id']}/refund", json={
        "amount": 25.00,
    })
    response = await client.get(f"/payments/{captured_payment['id']}/refunds")
    assert response.status_code == 200
    assert len(response.json()) == 1


@pytest.mark.asyncio
async def test_capture_updates_merchant_balance(client: AsyncClient, payment, merchant):
    await client.post(f"/payments/{payment['id']}/capture", json={})
    balance_response = await client.get(f"/merchants/{merchant['id']}/balance")
    assert balance_response.json()["balance"] == 100.00


@pytest.mark.asyncio
async def test_refund_updates_merchant_balance(client: AsyncClient, captured_payment, merchant):
    await client.post(f"/payments/{captured_payment['id']}/refund", json={
        "amount": 40.00,
    })
    balance_response = await client.get(f"/merchants/{merchant['id']}/balance")
    assert balance_response.json()["balance"] == 60.00
