import pytest
from httpx import AsyncClient

from app.main import app, get_app_version


@pytest.mark.asyncio
async def test_version(client: AsyncClient):
    response = await client.get("/version")
    assert response.status_code == 200
    data = response.json()
    assert data["version"] == get_app_version()


@pytest.mark.asyncio
async def test_health(client: AsyncClient):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


@pytest.mark.asyncio
async def test_root_version_matches_app_metadata(client: AsyncClient):
    response = await client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["version"] == get_app_version()
    assert data["version"] == app.version
