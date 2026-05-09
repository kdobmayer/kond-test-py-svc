import secrets
import hashlib
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Merchant, AuditLog
from app.schemas import MerchantCreate, MerchantUpdate, MerchantResponse, MerchantListResponse

router = APIRouter(prefix="/merchants", tags=["merchants"])


def generate_api_key() -> str:
    return f"pk_{secrets.token_hex(24)}"


def generate_api_secret() -> str:
    return f"sk_{secrets.token_hex(32)}"


@router.post("", response_model=MerchantResponse, status_code=201)
async def create_merchant(data: MerchantCreate, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(Merchant).where(Merchant.email == data.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Merchant with this email already exists")

    merchant = Merchant(
        name=data.name,
        email=data.email,
        currency=data.currency,
        api_key=generate_api_key(),
        api_secret=generate_api_secret(),
    )
    db.add(merchant)
    await db.flush()

    audit = AuditLog(
        entity_type="merchant",
        entity_id=merchant.id,
        action="created",
        details=f"Merchant '{merchant.name}' created",
    )
    db.add(audit)
    await db.flush()

    return merchant


@router.get("", response_model=MerchantListResponse)
async def list_merchants(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    is_active: bool | None = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(Merchant)
    count_query = select(func.count(Merchant.id))

    if is_active is not None:
        query = query.where(Merchant.is_active == is_active)
        count_query = count_query.where(Merchant.is_active == is_active)

    total_result = await db.execute(count_query)
    total = total_result.scalar()

    result = await db.execute(query.offset(skip).limit(limit))
    merchants = result.scalars().all()

    return MerchantListResponse(merchants=merchants, total=total)


@router.get("/{merchant_id}", response_model=MerchantResponse)
async def get_merchant(merchant_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Merchant).where(Merchant.id == merchant_id))
    merchant = result.scalar_one_or_none()
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")
    return merchant


@router.patch("/{merchant_id}", response_model=MerchantResponse)
async def update_merchant(
    merchant_id: str, data: MerchantUpdate, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Merchant).where(Merchant.id == merchant_id))
    merchant = result.scalar_one_or_none()
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(merchant, field, value)

    audit = AuditLog(
        entity_type="merchant",
        entity_id=merchant.id,
        action="updated",
        details=f"Fields updated: {', '.join(update_data.keys())}",
    )
    db.add(audit)
    await db.flush()

    return merchant


@router.delete("/{merchant_id}", status_code=204)
async def delete_merchant(merchant_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Merchant).where(Merchant.id == merchant_id))
    merchant = result.scalar_one_or_none()
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")

    await db.delete(merchant)

    audit = AuditLog(
        entity_type="merchant",
        entity_id=merchant_id,
        action="deleted",
        details=f"Merchant '{merchant.name}' deleted",
    )
    db.add(audit)
    await db.flush()


@router.post("/{merchant_id}/rotate-key", response_model=MerchantResponse)
async def rotate_api_key(merchant_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Merchant).where(Merchant.id == merchant_id))
    merchant = result.scalar_one_or_none()
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")

    merchant.api_key = generate_api_key()
    merchant.api_secret = generate_api_secret()

    audit = AuditLog(
        entity_type="merchant",
        entity_id=merchant.id,
        action="key_rotated",
        details="API key and secret rotated",
    )
    db.add(audit)
    await db.flush()

    return merchant


@router.get("/{merchant_id}/balance")
async def get_merchant_balance(merchant_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Merchant).where(Merchant.id == merchant_id))
    merchant = result.scalar_one_or_none()
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")

    return {
        "merchant_id": merchant.id,
        "balance": merchant.balance,
        "currency": merchant.currency,
    }
