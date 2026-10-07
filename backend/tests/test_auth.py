import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_new_organization(client: AsyncClient):
    """Test full registration workflow creates organization, owner user, default pipeline."""
    payload = {
        "organization_name": "Acme Innovations",
        "first_name": "John",
        "last_name": "Doe",
        "email": "john@acme.com",
        "password": "SecurePassword123!",
    }
    response = await client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["user"]["email"] == "john@acme.com"
    assert data["user"]["role"] == "OWNER"
    assert data["organization"]["name"] == "Acme Innovations"


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient, test_user_owner):
    """Test login with valid credentials returns tokens."""
    payload = {
        "email": "owner@alpha.com",
        "password": "password123",
    }
    response = await client.post("/api/v1/auth/login", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["user"]["email"] == "owner@alpha.com"


@pytest.mark.asyncio
async def test_login_invalid_password(client: AsyncClient, test_user_owner):
    """Test login failure on incorrect password."""
    payload = {
        "email": "owner@alpha.com",
        "password": "wrongpassword",
    }
    response = await client.post("/api/v1/auth/login", json=payload)
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_me_profile(client: AsyncClient, auth_headers_owner):
    """Test /api/v1/auth/me returns current user and tenant context."""
    response = await client.get("/api/v1/auth/me", headers=auth_headers_owner)
    assert response.status_code == 200
    data = response.json()
    assert data["user"]["email"] == "owner@alpha.com"
    assert data["organization"]["slug"] == "org-alpha"
