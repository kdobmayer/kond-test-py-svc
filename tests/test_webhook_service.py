"""Comprehensive tests for app/services/webhooks.py delivery logic."""
import json
import pytest
from datetime import datetime, timezone
from unittest.mock import patch, AsyncMock, MagicMock

import httpx
from sqlalchemy import select

from app.models import Merchant, WebhookEndpoint, WebhookDelivery, DeliveryStatus
from app.services.webhooks import (
    compute_signature,
    verify_signature,
    _attempt_delivery,
    dispatch_webhook_event,
)
from tests.conftest import TestSessionLocal


# ─── DB setup helpers ─────────────────────────────────────────────────────────

async def _make_merchant(db, suffix: str = "") -> Merchant:
    m = Merchant(
        name=f"Test Merchant{suffix}",
        email=f"test{suffix}@merchant.com",
        api_key=f"pk_test{suffix}",
        api_secret=f"sk_test{suffix}",
        balance=0.0,
        currency="USD",
    )
    db.add(m)
    await db.flush()
    return m


async def _make_endpoint(
    db,
    merchant_id: str,
    *,
    events=None,
    secret: str = "whsec_test",
    url: str = "https://hooks.example.com/recv",
    is_active: bool = True,
) -> WebhookEndpoint:
    ep = WebhookEndpoint(
        merchant_id=merchant_id,
        url=url,
        secret=secret,
        events=json.dumps(events or ["payment.created"]),
        is_active=is_active,
    )
    db.add(ep)
    await db.flush()
    return ep


async def _make_delivery(
    db, endpoint_id: str, event_type: str = "payment.created"
) -> WebhookDelivery:
    payload_str = json.dumps({
        "event_type": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": {"amount": 100},
    })
    d = WebhookDelivery(
        endpoint_id=endpoint_id,
        event_type=event_type,
        payload=payload_str,
        status=DeliveryStatus.PENDING,
    )
    db.add(d)
    await db.flush()
    return d


def _wire_mock_client(mock_cls, responses) -> AsyncMock:
    """Configure a patched httpx.AsyncClient mock with given responses.

    responses: int status code, Exception instance, or list of either.
    """
    mock_client = AsyncMock()
    if isinstance(responses, list):
        side_effects = [
            r if isinstance(r, BaseException) else MagicMock(status_code=r)
            for r in responses
        ]
        mock_client.post.side_effect = side_effects
    elif isinstance(responses, BaseException):
        mock_client.post.side_effect = responses
    else:
        mock_client.post.return_value = MagicMock(status_code=responses)
    mock_cls.return_value.__aenter__.return_value = mock_client
    return mock_client


# ─── HMAC signature unit tests ────────────────────────────────────────────────

def test_compute_signature_is_deterministic():
    assert compute_signature('{"x": 1}', "s") == compute_signature('{"x": 1}', "s")


def test_compute_signature_differs_by_payload():
    assert compute_signature('{"x": 1}', "s") != compute_signature('{"x": 2}', "s")


def test_compute_signature_differs_by_secret():
    assert compute_signature('{"x": 1}', "s1") != compute_signature('{"x": 1}', "s2")


def test_compute_signature_matches_known_hmac():
    import hashlib
    import hmac as _hmac
    payload, secret = '{"event": "payment.created"}', "mysecret"
    expected = _hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    assert compute_signature(payload, secret) == expected


def test_verify_signature_accepts_correct():
    payload, secret = '{"amount": 100}', "webhook-secret"
    assert verify_signature(payload, compute_signature(payload, secret), secret)


def test_verify_signature_rejects_wrong_signature():
    assert not verify_signature('{"amount": 100}', "bad-sig", "secret")


def test_verify_signature_rejects_tampered_payload():
    secret = "webhook-secret"
    sig = compute_signature('{"amount": 100}', secret)
    assert not verify_signature('{"amount": 200}', sig, secret)


# ─── _attempt_delivery: successful delivery ───────────────────────────────────

@pytest.mark.asyncio
@patch("app.services.webhooks._async_sleep", new_callable=AsyncMock)
async def test_successful_delivery_marks_delivered(mock_sleep):
    async with TestSessionLocal() as db:
        merchant = await _make_merchant(db)
        endpoint = await _make_endpoint(db, merchant.id)
        delivery = await _make_delivery(db, endpoint.id)

        with patch("app.services.webhooks.httpx.AsyncClient") as mock_cls:
            _wire_mock_client(mock_cls, 200)
            await _attempt_delivery(db, delivery, endpoint)

        assert delivery.status == DeliveryStatus.DELIVERED
        assert delivery.attempts == 1
        assert delivery.response_code == 200
        assert delivery.delivered_at is not None
        mock_sleep.assert_not_called()
        await db.commit()


@pytest.mark.asyncio
@patch("app.services.webhooks._async_sleep", new_callable=AsyncMock)
async def test_successful_delivery_sets_delivered_at(mock_sleep):
    before = datetime.now(timezone.utc)
    async with TestSessionLocal() as db:
        merchant = await _make_merchant(db)
        endpoint = await _make_endpoint(db, merchant.id)
        delivery = await _make_delivery(db, endpoint.id)

        with patch("app.services.webhooks.httpx.AsyncClient") as mock_cls:
            _wire_mock_client(mock_cls, 201)
            await _attempt_delivery(db, delivery, endpoint)

        assert delivery.delivered_at >= before
        await db.commit()


# ─── _attempt_delivery: retry behavior ───────────────────────────────────────

@pytest.mark.asyncio
@patch("app.services.webhooks._async_sleep", new_callable=AsyncMock)
async def test_server_error_retries_3_times(mock_sleep):
    async with TestSessionLocal() as db:
        merchant = await _make_merchant(db)
        endpoint = await _make_endpoint(db, merchant.id)
        delivery = await _make_delivery(db, endpoint.id)

        with patch("app.services.webhooks.httpx.AsyncClient") as mock_cls:
            _wire_mock_client(mock_cls, 500)
            await _attempt_delivery(db, delivery, endpoint)

        assert delivery.status == DeliveryStatus.FAILED
        assert delivery.attempts == 3
        assert delivery.response_code == 500
        await db.commit()


@pytest.mark.asyncio
@patch("app.services.webhooks._async_sleep", new_callable=AsyncMock)
async def test_backoff_schedule_is_exponential(mock_sleep):
    """Sleep is 2^0=1s after attempt 0, 2^1=2s after attempt 1, none after attempt 2."""
    async with TestSessionLocal() as db:
        merchant = await _make_merchant(db)
        endpoint = await _make_endpoint(db, merchant.id)
        delivery = await _make_delivery(db, endpoint.id)

        with patch("app.services.webhooks.httpx.AsyncClient") as mock_cls:
            _wire_mock_client(mock_cls, 503)
            await _attempt_delivery(db, delivery, endpoint)

        assert mock_sleep.call_count == 2
        mock_sleep.assert_any_call(1)
        mock_sleep.assert_any_call(2)
        await db.commit()


@pytest.mark.asyncio
@patch("app.services.webhooks._async_sleep", new_callable=AsyncMock)
async def test_succeeds_on_second_attempt(mock_sleep):
    async with TestSessionLocal() as db:
        merchant = await _make_merchant(db)
        endpoint = await _make_endpoint(db, merchant.id)
        delivery = await _make_delivery(db, endpoint.id)

        with patch("app.services.webhooks.httpx.AsyncClient") as mock_cls:
            _wire_mock_client(mock_cls, [503, 200])
            await _attempt_delivery(db, delivery, endpoint)

        assert delivery.status == DeliveryStatus.DELIVERED
        assert delivery.attempts == 2
        assert delivery.response_code == 200
        assert delivery.delivered_at is not None
        mock_sleep.assert_called_once_with(1)
        await db.commit()


# ─── _attempt_delivery: HTTP error / timeout handling ────────────────────────

@pytest.mark.asyncio
@patch("app.services.webhooks._async_sleep", new_callable=AsyncMock)
async def test_request_error_triggers_3_retries(mock_sleep):
    """httpx.RequestError (connection refused) exhausts all 3 attempts → FAILED."""
    async with TestSessionLocal() as db:
        merchant = await _make_merchant(db)
        endpoint = await _make_endpoint(db, merchant.id)
        delivery = await _make_delivery(db, endpoint.id)

        with patch("app.services.webhooks.httpx.AsyncClient") as mock_cls:
            _wire_mock_client(mock_cls, httpx.ConnectError("connection refused"))
            await _attempt_delivery(db, delivery, endpoint)

        assert delivery.status == DeliveryStatus.FAILED
        assert delivery.attempts == 3
        assert delivery.response_code is None
        assert mock_sleep.call_count == 2
        await db.commit()


@pytest.mark.asyncio
@patch("app.services.webhooks._async_sleep", new_callable=AsyncMock)
async def test_timeout_triggers_3_retries(mock_sleep):
    """httpx.TimeoutException exhausts all 3 attempts, response_code stays None → FAILED."""
    async with TestSessionLocal() as db:
        merchant = await _make_merchant(db)
        endpoint = await _make_endpoint(db, merchant.id)
        delivery = await _make_delivery(db, endpoint.id)

        with patch("app.services.webhooks.httpx.AsyncClient") as mock_cls:
            _wire_mock_client(mock_cls, httpx.ReadTimeout("timed out"))
            await _attempt_delivery(db, delivery, endpoint)

        assert delivery.status == DeliveryStatus.FAILED
        assert delivery.attempts == 3
        assert delivery.response_code is None
        assert mock_sleep.call_count == 2
        await db.commit()


@pytest.mark.asyncio
@patch("app.services.webhooks._async_sleep", new_callable=AsyncMock)
async def test_recovers_after_mixed_errors(mock_sleep):
    """Timeout → network error → 200 OK results in DELIVERED after 3 attempts."""
    async with TestSessionLocal() as db:
        merchant = await _make_merchant(db)
        endpoint = await _make_endpoint(db, merchant.id)
        delivery = await _make_delivery(db, endpoint.id)

        with patch("app.services.webhooks.httpx.AsyncClient") as mock_cls:
            _wire_mock_client(mock_cls, [
                httpx.ReadTimeout("timeout"),
                httpx.ConnectError("refused"),
                200,
            ])
            await _attempt_delivery(db, delivery, endpoint)

        assert delivery.status == DeliveryStatus.DELIVERED
        assert delivery.attempts == 3
        assert delivery.response_code == 200
        await db.commit()


# ─── _attempt_delivery: HMAC signature in request headers ────────────────────

@pytest.mark.asyncio
@patch("app.services.webhooks._async_sleep", new_callable=AsyncMock)
async def test_request_contains_correct_hmac_signature(mock_sleep):
    secret = "super-secret-key-123"
    async with TestSessionLocal() as db:
        merchant = await _make_merchant(db)
        endpoint = await _make_endpoint(db, merchant.id, secret=secret)
        delivery = await _make_delivery(db, endpoint.id)

        captured: dict = {}

        async def _spy_post(url, content=None, headers=None):
            captured.update({"url": url, "content": content, "headers": dict(headers or {})})
            return MagicMock(status_code=200)

        with patch("app.services.webhooks.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.post = _spy_post
            mock_cls.return_value.__aenter__.return_value = mock_client
            await _attempt_delivery(db, delivery, endpoint)

        expected_sig = compute_signature(delivery.payload, secret)
        h = captured["headers"]
        assert h["X-Webhook-Signature"] == expected_sig
        assert h["X-Webhook-Event"] == delivery.event_type
        assert h["X-Webhook-Delivery-Id"] == delivery.id
        assert h["Content-Type"] == "application/json"
        assert captured["content"] == delivery.payload
        await db.commit()


# ─── _attempt_delivery: delivery status recording ────────────────────────────

@pytest.mark.asyncio
@patch("app.services.webhooks._async_sleep", new_callable=AsyncMock)
async def test_last_attempt_at_is_recorded(mock_sleep):
    before = datetime.now(timezone.utc)
    async with TestSessionLocal() as db:
        merchant = await _make_merchant(db)
        endpoint = await _make_endpoint(db, merchant.id)
        delivery = await _make_delivery(db, endpoint.id)

        with patch("app.services.webhooks.httpx.AsyncClient") as mock_cls:
            _wire_mock_client(mock_cls, 500)
            await _attempt_delivery(db, delivery, endpoint)

        assert delivery.last_attempt_at is not None
        assert delivery.last_attempt_at >= before
        await db.commit()


@pytest.mark.asyncio
@patch("app.services.webhooks._async_sleep", new_callable=AsyncMock)
async def test_response_code_recorded_on_http_failure(mock_sleep):
    async with TestSessionLocal() as db:
        merchant = await _make_merchant(db)
        endpoint = await _make_endpoint(db, merchant.id)
        delivery = await _make_delivery(db, endpoint.id)

        with patch("app.services.webhooks.httpx.AsyncClient") as mock_cls:
            _wire_mock_client(mock_cls, 422)
            await _attempt_delivery(db, delivery, endpoint)

        assert delivery.response_code == 422
        await db.commit()


# ─── dispatch_webhook_event integration tests ────────────────────────────────

@pytest.mark.asyncio
@patch("app.services.webhooks._async_sleep", new_callable=AsyncMock)
async def test_dispatch_creates_and_delivers(mock_sleep):
    async with TestSessionLocal() as db:
        merchant = await _make_merchant(db)
        await _make_endpoint(db, merchant.id, events=["payment.created"])
        merchant_id = merchant.id
        await db.commit()

    with patch("app.services.webhooks.httpx.AsyncClient") as mock_cls:
        _wire_mock_client(mock_cls, 200)
        await dispatch_webhook_event(
            merchant_id=merchant_id,
            event_type="payment.created",
            payload={"amount": 100, "currency": "USD"},
        )

    async with TestSessionLocal() as db:
        result = await db.execute(select(WebhookDelivery))
        deliveries = result.scalars().all()

    assert len(deliveries) == 1
    assert deliveries[0].status == DeliveryStatus.DELIVERED
    assert deliveries[0].event_type == "payment.created"
    assert deliveries[0].attempts == 1


@pytest.mark.asyncio
@patch("app.services.webhooks._async_sleep", new_callable=AsyncMock)
async def test_dispatch_failed_delivery_persisted(mock_sleep):
    async with TestSessionLocal() as db:
        merchant = await _make_merchant(db)
        await _make_endpoint(db, merchant.id, events=["payment.created"])
        merchant_id = merchant.id
        await db.commit()

    with patch("app.services.webhooks.httpx.AsyncClient") as mock_cls:
        _wire_mock_client(mock_cls, 500)
        await dispatch_webhook_event(
            merchant_id=merchant_id,
            event_type="payment.created",
            payload={"amount": 100},
        )

    async with TestSessionLocal() as db:
        result = await db.execute(select(WebhookDelivery))
        delivery = result.scalar_one()

    assert delivery.status == DeliveryStatus.FAILED
    assert delivery.attempts == 3
    assert delivery.response_code == 500


@pytest.mark.asyncio
async def test_dispatch_skips_inactive_endpoint():
    async with TestSessionLocal() as db:
        merchant = await _make_merchant(db)
        await _make_endpoint(db, merchant.id, is_active=False)
        merchant_id = merchant.id
        await db.commit()

    with patch("app.services.webhooks.httpx.AsyncClient") as mock_cls:
        await dispatch_webhook_event(
            merchant_id=merchant_id,
            event_type="payment.created",
            payload={"amount": 100},
        )
        mock_cls.assert_not_called()

    async with TestSessionLocal() as db:
        result = await db.execute(select(WebhookDelivery))
        assert result.scalars().all() == []


@pytest.mark.asyncio
async def test_dispatch_skips_unsubscribed_event():
    async with TestSessionLocal() as db:
        merchant = await _make_merchant(db)
        await _make_endpoint(db, merchant.id, events=["payment.voided"])
        merchant_id = merchant.id
        await db.commit()

    with patch("app.services.webhooks.httpx.AsyncClient") as mock_cls:
        await dispatch_webhook_event(
            merchant_id=merchant_id,
            event_type="payment.created",
            payload={"amount": 100},
        )
        mock_cls.assert_not_called()

    async with TestSessionLocal() as db:
        result = await db.execute(select(WebhookDelivery))
        assert result.scalars().all() == []


@pytest.mark.asyncio
@patch("app.services.webhooks._async_sleep", new_callable=AsyncMock)
async def test_dispatch_delivers_to_all_matching_endpoints(mock_sleep):
    async with TestSessionLocal() as db:
        merchant = await _make_merchant(db)
        await _make_endpoint(db, merchant.id, url="https://ep1.example.com/hook")
        await _make_endpoint(db, merchant.id, url="https://ep2.example.com/hook")
        merchant_id = merchant.id
        await db.commit()

    with patch("app.services.webhooks.httpx.AsyncClient") as mock_cls:
        _wire_mock_client(mock_cls, 200)
        await dispatch_webhook_event(
            merchant_id=merchant_id,
            event_type="payment.created",
            payload={"amount": 100},
        )

    async with TestSessionLocal() as db:
        result = await db.execute(select(WebhookDelivery))
        deliveries = result.scalars().all()

    assert len(deliveries) == 2
    assert all(d.status == DeliveryStatus.DELIVERED for d in deliveries)


@pytest.mark.asyncio
@patch("app.services.webhooks._async_sleep", new_callable=AsyncMock)
async def test_dispatch_payload_structure(mock_sleep):
    """Stored payload JSON contains event_type, timestamp, and nested data."""
    async with TestSessionLocal() as db:
        merchant = await _make_merchant(db)
        await _make_endpoint(db, merchant.id)
        merchant_id = merchant.id
        await db.commit()

    with patch("app.services.webhooks.httpx.AsyncClient") as mock_cls:
        _wire_mock_client(mock_cls, 200)
        await dispatch_webhook_event(
            merchant_id=merchant_id,
            event_type="payment.created",
            payload={"amount": 99.99, "currency": "EUR"},
        )

    async with TestSessionLocal() as db:
        result = await db.execute(select(WebhookDelivery))
        delivery = result.scalar_one()

    parsed = json.loads(delivery.payload)
    assert parsed["event_type"] == "payment.created"
    assert "timestamp" in parsed
    assert parsed["data"]["amount"] == 99.99
    assert parsed["data"]["currency"] == "EUR"


@pytest.mark.asyncio
async def test_dispatch_skips_malformed_subscription_config():
    async with TestSessionLocal() as db:
        merchant = await _make_merchant(db)
        good_endpoint = await _make_endpoint(db, merchant.id)
        bad_endpoint = WebhookEndpoint(
            merchant_id=merchant.id,
            url="https://bad.example.com/hook",
            secret="whsec_bad",
            events="{not-json",
            is_active=True,
        )
        db.add(bad_endpoint)
        merchant_id = merchant.id
        await db.commit()

    with patch("app.services.webhooks.httpx.AsyncClient") as mock_cls:
        _wire_mock_client(mock_cls, 200)
        await dispatch_webhook_event(
            merchant_id=merchant_id,
            event_type="payment.created",
            payload={"amount": 100},
        )

    async with TestSessionLocal() as db:
        result = await db.execute(select(WebhookDelivery))
        deliveries = result.scalars().all()

    assert len(deliveries) == 1
    assert deliveries[0].endpoint_id == good_endpoint.id


@pytest.mark.asyncio
@patch("app.services.webhooks._async_sleep", new_callable=AsyncMock)
async def test_client_error_fails_without_retry(mock_sleep):
    async with TestSessionLocal() as db:
        merchant = await _make_merchant(db)
        endpoint = await _make_endpoint(db, merchant.id)
        delivery = await _make_delivery(db, endpoint.id)

        with patch("app.services.webhooks.httpx.AsyncClient") as mock_cls:
            _wire_mock_client(mock_cls, 422)
            await _attempt_delivery(db, delivery, endpoint)

        assert delivery.status == DeliveryStatus.FAILED
        assert delivery.attempts == 1
        assert delivery.response_code == 422
        mock_sleep.assert_not_called()
        await db.commit()
