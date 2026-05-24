import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_dispute_on_captured_payment(client: AsyncClient, captured_payment):
    response = await client.post(f"/payments/{captured_payment['id']}/dispute", json={
        "reason": "Item not received",
        "evidence": "Customer reported non-delivery",
    })
    assert response.status_code == 201
    data = response.json()
    assert data["payment_id"] == captured_payment["id"]
    assert data["reason"] == "Item not received"
    assert data["evidence"] == "Customer reported non-delivery"
    assert data["status"] == "open"
    assert data["amount"] == 100.00
    assert data["refund_id"] is None


@pytest.mark.asyncio
async def test_create_dispute_defaults_to_full_available_amount(client: AsyncClient, captured_payment):
    # Partial refund first
    await client.post(f"/payments/{captured_payment['id']}/refund", json={"amount": 30.00})
    response = await client.post(f"/payments/{captured_payment['id']}/dispute", json={
        "reason": "Product defective",
    })
    assert response.status_code == 201
    data = response.json()
    assert data["amount"] == 70.00


@pytest.mark.asyncio
async def test_create_dispute_with_explicit_amount(client: AsyncClient, captured_payment):
    response = await client.post(f"/payments/{captured_payment['id']}/dispute", json={
        "reason": "Partial charge dispute",
        "amount": 40.00,
    })
    assert response.status_code == 201
    assert response.json()["amount"] == 40.00


@pytest.mark.asyncio
async def test_create_dispute_payment_not_found(client: AsyncClient):
    response = await client.post("/payments/nonexistent/dispute", json={
        "reason": "Fraud",
    })
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_dispute_wrong_status_authorized(client: AsyncClient, payment):
    response = await client.post(f"/payments/{payment['id']}/dispute", json={
        "reason": "Fraud",
    })
    assert response.status_code == 400
    assert "authorized" in response.json()["detail"]


@pytest.mark.asyncio
async def test_create_dispute_wrong_status_voided(client: AsyncClient, payment):
    await client.post(f"/payments/{payment['id']}/void")
    response = await client.post(f"/payments/{payment['id']}/dispute", json={
        "reason": "Fraud",
    })
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_create_dispute_amount_exceeds_available(client: AsyncClient, captured_payment):
    response = await client.post(f"/payments/{captured_payment['id']}/dispute", json={
        "reason": "Fraud",
        "amount": 200.00,
    })
    assert response.status_code == 400
    assert "exceeds available" in response.json()["detail"]


@pytest.mark.asyncio
async def test_create_dispute_duplicate_active_dispute(client: AsyncClient, captured_payment):
    await client.post(f"/payments/{captured_payment['id']}/dispute", json={
        "reason": "First dispute",
    })
    response = await client.post(f"/payments/{captured_payment['id']}/dispute", json={
        "reason": "Second dispute",
    })
    assert response.status_code == 400
    assert "active dispute" in response.json()["detail"]


@pytest.mark.asyncio
async def test_create_dispute_on_partially_refunded_payment(client: AsyncClient, captured_payment):
    await client.post(f"/payments/{captured_payment['id']}/refund", json={"amount": 20.00})
    response = await client.post(f"/payments/{captured_payment['id']}/dispute", json={
        "reason": "Remaining amount disputed",
    })
    assert response.status_code == 201
    assert response.json()["amount"] == 80.00


@pytest.mark.asyncio
async def test_list_disputes_empty(client: AsyncClient):
    response = await client.get("/disputes")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["disputes"] == []


@pytest.mark.asyncio
async def test_list_disputes_returns_created(client: AsyncClient, captured_payment):
    await client.post(f"/payments/{captured_payment['id']}/dispute", json={"reason": "Test"})
    response = await client.get("/disputes")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["disputes"][0]["reason"] == "Test"


@pytest.mark.asyncio
async def test_list_disputes_filter_by_status(client: AsyncClient, captured_payment):
    await client.post(f"/payments/{captured_payment['id']}/dispute", json={"reason": "Open dispute"})
    response = await client.get("/disputes?status=open")
    assert response.status_code == 200
    assert response.json()["total"] == 1

    response = await client.get("/disputes?status=accepted")
    assert response.status_code == 200
    assert response.json()["total"] == 0


@pytest.mark.asyncio
async def test_list_disputes_filter_by_merchant(client: AsyncClient, captured_payment, merchant):
    await client.post(f"/payments/{captured_payment['id']}/dispute", json={"reason": "Test"})
    response = await client.get(f"/disputes?merchant_id={merchant['id']}")
    assert response.status_code == 200
    assert response.json()["total"] == 1

    response = await client.get("/disputes?merchant_id=nonexistent")
    assert response.status_code == 200
    assert response.json()["total"] == 0


@pytest.mark.asyncio
async def test_list_disputes_pagination(client: AsyncClient, merchant):
    # Create two separate captured payments for two disputes
    p1 = (await client.post("/payments", json={
        "merchant_id": merchant["id"], "amount": 10.00, "currency": "USD",
    })).json()
    p2 = (await client.post("/payments", json={
        "merchant_id": merchant["id"], "amount": 20.00, "currency": "USD",
    })).json()
    await client.post(f"/payments/{p1['id']}/capture", json={})
    await client.post(f"/payments/{p2['id']}/capture", json={})
    await client.post(f"/payments/{p1['id']}/dispute", json={"reason": "D1"})
    await client.post(f"/payments/{p2['id']}/dispute", json={"reason": "D2"})

    response = await client.get("/disputes?limit=1&skip=0")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert len(data["disputes"]) == 1


@pytest.mark.asyncio
async def test_resolve_dispute_rejected(client: AsyncClient, captured_payment):
    dispute = (await client.post(f"/payments/{captured_payment['id']}/dispute", json={
        "reason": "Fraud claim",
    })).json()

    response = await client.patch(f"/disputes/{dispute['id']}/resolve", json={
        "resolution": "rejected",
        "resolution_note": "Evidence insufficient",
    })
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "rejected"
    assert data["resolution_note"] == "Evidence insufficient"
    assert data["refund_id"] is None


@pytest.mark.asyncio
async def test_resolve_dispute_accepted_creates_refund(client: AsyncClient, captured_payment):
    dispute = (await client.post(f"/payments/{captured_payment['id']}/dispute", json={
        "reason": "Item not delivered",
    })).json()

    response = await client.patch(f"/disputes/{dispute['id']}/resolve", json={
        "resolution": "accepted",
        "resolution_note": "Customer confirmed",
    })
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "accepted"
    assert data["refund_id"] is not None

    payment_response = await client.get(f"/payments/{captured_payment['id']}")
    assert payment_response.json()["status"] == "refunded"
    assert payment_response.json()["refunded_amount"] == 100.00


@pytest.mark.asyncio
async def test_resolve_dispute_accepted_partial_amount(client: AsyncClient, captured_payment):
    dispute = (await client.post(f"/payments/{captured_payment['id']}/dispute", json={
        "reason": "Partial issue",
        "amount": 60.00,
    })).json()

    await client.patch(f"/disputes/{dispute['id']}/resolve", json={"resolution": "accepted"})

    payment_response = await client.get(f"/payments/{captured_payment['id']}")
    assert payment_response.json()["status"] == "partially_refunded"
    assert payment_response.json()["refunded_amount"] == 60.00


@pytest.mark.asyncio
async def test_resolve_dispute_accepted_updates_merchant_balance(
    client: AsyncClient, captured_payment, merchant
):
    balance_before = (await client.get(f"/merchants/{merchant['id']}/balance")).json()["balance"]
    assert balance_before == 100.00

    dispute = (await client.post(f"/payments/{captured_payment['id']}/dispute", json={
        "reason": "Fraud",
    })).json()

    await client.patch(f"/disputes/{dispute['id']}/resolve", json={"resolution": "accepted"})

    balance_after = (await client.get(f"/merchants/{merchant['id']}/balance")).json()["balance"]
    assert balance_after == 0.00


@pytest.mark.asyncio
async def test_resolve_dispute_not_found(client: AsyncClient):
    response = await client.patch("/disputes/nonexistent/resolve", json={
        "resolution": "rejected",
    })
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_resolve_already_resolved_dispute(client: AsyncClient, captured_payment):
    dispute = (await client.post(f"/payments/{captured_payment['id']}/dispute", json={
        "reason": "Test",
    })).json()

    await client.patch(f"/disputes/{dispute['id']}/resolve", json={"resolution": "rejected"})
    response = await client.patch(f"/disputes/{dispute['id']}/resolve", json={
        "resolution": "accepted",
    })
    assert response.status_code == 400
    assert "rejected" in response.json()["detail"]


@pytest.mark.asyncio
async def test_resolve_dispute_invalid_resolution(client: AsyncClient, captured_payment):
    dispute = (await client.post(f"/payments/{captured_payment['id']}/dispute", json={
        "reason": "Test",
    })).json()

    response = await client.patch(f"/disputes/{dispute['id']}/resolve", json={
        "resolution": "pending",
    })
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_new_dispute_after_previous_resolved(client: AsyncClient, captured_payment):
    dispute = (await client.post(f"/payments/{captured_payment['id']}/dispute", json={
        "reason": "First claim",
        "amount": 40.00,
    })).json()

    await client.patch(f"/disputes/{dispute['id']}/resolve", json={"resolution": "rejected"})

    response = await client.post(f"/payments/{captured_payment['id']}/dispute", json={
        "reason": "Second claim",
        "amount": 40.00,
    })
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_create_dispute_invalid_amount_decimal(client: AsyncClient, captured_payment):
    response = await client.post(f"/payments/{captured_payment['id']}/dispute", json={
        "reason": "Fraud",
        "amount": 10.555,
    })
    assert response.status_code == 422
