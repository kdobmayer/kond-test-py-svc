import hashlib
import hmac
import json
import time
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models import WebhookEndpoint, WebhookDelivery, DeliveryStatus


def compute_signature(payload: str, secret: str) -> str:
    """Compute HMAC-SHA256 signature for webhook payload."""
    return hmac.new(
        secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify_signature(payload: str, signature: str, secret: str) -> bool:
    """Verify HMAC-SHA256 webhook signature."""
    expected = hmac.new(
        secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


async def dispatch_webhook_event(
    merchant_id: str,
    event_type: str,
    payload: dict,
):
    """Dispatch webhook event to all registered endpoints for a merchant.

    This is called as a background task after payment events.
    """
    async with async_session() as db:
        result = await db.execute(
            select(WebhookEndpoint).where(
                WebhookEndpoint.merchant_id == merchant_id,
                WebhookEndpoint.is_active == True,
            )
        )
        endpoints = result.scalars().all()

        for endpoint in endpoints:
            # Check if endpoint is subscribed to this event type
            subscribed_events = json.loads(endpoint.events)
            if event_type not in subscribed_events:
                continue

            payload_str = json.dumps({
                "event_type": event_type,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "data": payload,
            })

            delivery = WebhookDelivery(
                endpoint_id=endpoint.id,
                event_type=event_type,
                payload=payload_str,
                status=DeliveryStatus.PENDING,
            )
            db.add(delivery)
            await db.flush()

            # Attempt delivery (no tests for this — intentional rough edge)
            await _attempt_delivery(db, delivery, endpoint)

        await db.commit()


async def _attempt_delivery(
    db: AsyncSession,
    delivery: WebhookDelivery,
    endpoint: WebhookEndpoint,
):
    """Attempt to deliver a webhook. Retries up to 3 times with backoff."""
    max_attempts = 3

    for attempt in range(max_attempts):
        delivery.attempts += 1
        delivery.last_attempt_at = datetime.now(timezone.utc)

        try:
            signature = compute_signature(delivery.payload, endpoint.secret)
            headers = {
                "Content-Type": "application/json",
                "X-Webhook-Signature": signature,
                "X-Webhook-Event": delivery.event_type,
                "X-Webhook-Delivery-Id": delivery.id,
            }

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    endpoint.url,
                    content=delivery.payload,
                    headers=headers,
                )

            delivery.response_code = response.status_code

            if 200 <= response.status_code < 300:
                delivery.status = DeliveryStatus.DELIVERED
                delivery.delivered_at = datetime.now(timezone.utc)
                await db.flush()
                return
        except (httpx.RequestError, httpx.TimeoutException):
            delivery.response_code = None

        # Backoff before retry
        if attempt < max_attempts - 1:
            await _async_sleep(2 ** attempt)

    delivery.status = DeliveryStatus.FAILED
    await db.flush()


async def _async_sleep(seconds: float):
    """Async sleep wrapper for testability."""
    import asyncio
    await asyncio.sleep(seconds)
