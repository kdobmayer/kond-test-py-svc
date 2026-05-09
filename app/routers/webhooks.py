import json
import secrets
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import WebhookEndpoint, WebhookDelivery, Merchant
from app.schemas import (
    WebhookEndpointCreate, WebhookEndpointUpdate,
    WebhookEndpointResponse, WebhookDeliveryResponse,
    WebhookVerifyRequest, WebhookVerifyResponse,
)
from app.services.webhooks import verify_signature

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/endpoints", response_model=WebhookEndpointResponse, status_code=201)
async def create_webhook_endpoint(
    data: WebhookEndpointCreate, db: AsyncSession = Depends(get_db)
):
    # Verify merchant exists
    merchant_result = await db.execute(
        select(Merchant).where(Merchant.id == data.merchant_id)
    )
    if not merchant_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Merchant not found")

    endpoint = WebhookEndpoint(
        merchant_id=data.merchant_id,
        url=data.url,
        secret=secrets.token_hex(32),
        events=json.dumps(data.events),
        is_active=True,
    )
    db.add(endpoint)
    await db.flush()

    return _endpoint_to_response(endpoint)


@router.get("/endpoints", response_model=list[WebhookEndpointResponse])
async def list_webhook_endpoints(
    merchant_id: str | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    query = select(WebhookEndpoint)
    if merchant_id:
        query = query.where(WebhookEndpoint.merchant_id == merchant_id)

    result = await db.execute(query.offset(skip).limit(limit))
    endpoints = result.scalars().all()
    return [_endpoint_to_response(ep) for ep in endpoints]


@router.get("/endpoints/{endpoint_id}", response_model=WebhookEndpointResponse)
async def get_webhook_endpoint(endpoint_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(WebhookEndpoint).where(WebhookEndpoint.id == endpoint_id)
    )
    endpoint = result.scalar_one_or_none()
    if not endpoint:
        raise HTTPException(status_code=404, detail="Webhook endpoint not found")
    return _endpoint_to_response(endpoint)


@router.patch("/endpoints/{endpoint_id}", response_model=WebhookEndpointResponse)
async def update_webhook_endpoint(
    endpoint_id: str,
    data: WebhookEndpointUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(WebhookEndpoint).where(WebhookEndpoint.id == endpoint_id)
    )
    endpoint = result.scalar_one_or_none()
    if not endpoint:
        raise HTTPException(status_code=404, detail="Webhook endpoint not found")

    update_data = data.model_dump(exclude_unset=True)
    if "events" in update_data and update_data["events"] is not None:
        update_data["events"] = json.dumps(update_data["events"])

    for field, value in update_data.items():
        setattr(endpoint, field, value)

    await db.flush()
    return _endpoint_to_response(endpoint)


@router.delete("/endpoints/{endpoint_id}", status_code=204)
async def delete_webhook_endpoint(endpoint_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(WebhookEndpoint).where(WebhookEndpoint.id == endpoint_id)
    )
    endpoint = result.scalar_one_or_none()
    if not endpoint:
        raise HTTPException(status_code=404, detail="Webhook endpoint not found")
    await db.delete(endpoint)


@router.get("/deliveries", response_model=list[WebhookDeliveryResponse])
async def list_deliveries(
    endpoint_id: str | None = None,
    status: str | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    query = select(WebhookDelivery)
    if endpoint_id:
        query = query.where(WebhookDelivery.endpoint_id == endpoint_id)
    if status:
        query = query.where(WebhookDelivery.status == status)

    result = await db.execute(
        query.order_by(WebhookDelivery.created_at.desc()).offset(skip).limit(limit)
    )
    return result.scalars().all()


@router.post("/verify", response_model=WebhookVerifyResponse)
async def verify_webhook_signature(data: WebhookVerifyRequest):
    """Verify a webhook signature against a payload and secret."""
    is_valid = verify_signature(data.payload, data.signature, data.secret)
    return WebhookVerifyResponse(valid=is_valid)


def _endpoint_to_response(endpoint: WebhookEndpoint) -> WebhookEndpointResponse:
    return WebhookEndpointResponse(
        id=endpoint.id,
        merchant_id=endpoint.merchant_id,
        url=endpoint.url,
        events=json.loads(endpoint.events),
        is_active=endpoint.is_active,
        created_at=endpoint.created_at,
        updated_at=endpoint.updated_at,
    )
