from unittest.mock import patch

from httpx import AsyncClient

def _payment_payload(merchant_id: str) -> dict:
    return {
        "merchant_id": merchant_id,
        "amount": 10.00,
        "currency": "USD",
        "description": "Rate limit test",
    }


async def test_ten_requests_within_limit(client: AsyncClient, merchant: dict):
    api_key = merchant["api_key"]
    for _ in range(10):
        r = await client.post(
            "/payments",
            json=_payment_payload(merchant["id"]),
            headers={"X-API-Key": api_key},
        )
        assert r.status_code == 201


async def test_eleventh_request_returns_429(client: AsyncClient, merchant: dict):
    api_key = merchant["api_key"]
    for _ in range(10):
        await client.post(
            "/payments",
            json=_payment_payload(merchant["id"]),
            headers={"X-API-Key": api_key},
        )

    r = await client.post(
        "/payments",
        json=_payment_payload(merchant["id"]),
        headers={"X-API-Key": api_key},
    )
    assert r.status_code == 429
    assert "retry-after" in r.headers
    assert int(r.headers["retry-after"]) >= 1


async def test_different_api_keys_are_independent(client: AsyncClient, merchant: dict):
    """10 requests under key A and 10 under key B should all succeed."""
    api_key = merchant["api_key"]

    # Second merchant for a distinct key
    r2 = await client.post("/merchants", json={
        "name": "Merchant B",
        "email": "b@merchant.com",
        "currency": "USD",
    })
    merchant_b = r2.json()
    api_key_b = merchant_b["api_key"]

    for _ in range(10):
        ra = await client.post(
            "/payments",
            json=_payment_payload(merchant["id"]),
            headers={"X-API-Key": api_key},
        )
        assert ra.status_code == 201

        rb = await client.post(
            "/payments",
            json=_payment_payload(merchant_b["id"]),
            headers={"X-API-Key": api_key_b},
        )
        assert rb.status_code == 201


async def test_api_key_must_match_target_merchant(client: AsyncClient, merchant: dict):
    r2 = await client.post("/merchants", json={
        "name": "Merchant B",
        "email": "b@merchant.com",
        "currency": "USD",
    })
    merchant_b = r2.json()

    r = await client.post(
        "/payments",
        json=_payment_payload(merchant_b["id"]),
        headers={"X-API-Key": merchant["api_key"]},
    )
    assert r.status_code == 401


async def test_missing_api_key_returns_401(client: AsyncClient, merchant: dict):
    r = await client.post(
        "/payments",
        json=_payment_payload(merchant["id"]),
    )
    assert r.status_code == 401


async def test_window_slides_after_60_seconds(client: AsyncClient, merchant: dict):
    """After the window advances past 60s, previously rate-limited key is allowed."""
    api_key = merchant["api_key"]

    base_time = 1000.0

    with patch("app.rate_limit.time") as mock_time:
        mock_time.time.return_value = base_time

        for _ in range(10):
            r = await client.post(
                "/payments",
                json=_payment_payload(merchant["id"]),
                headers={"X-API-Key": api_key},
            )
            assert r.status_code == 201

        # Still within the window — should be rate limited
        r = await client.post(
            "/payments",
            json=_payment_payload(merchant["id"]),
            headers={"X-API-Key": api_key},
        )
        assert r.status_code == 429

        # Advance clock by 61 seconds — all old timestamps now expire
        mock_time.time.return_value = base_time + 61

        r = await client.post(
            "/payments",
            json=_payment_payload(merchant["id"]),
            headers={"X-API-Key": api_key},
        )
        assert r.status_code == 201
