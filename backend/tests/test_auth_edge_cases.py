from datetime import datetime, timedelta, timezone
import jwt
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.security import create_access_token, hash_password
from app.modules.users.models import User


@pytest.mark.asyncio
async def test_deactivated_user_cannot_access_api(client: AsyncClient, db_session: AsyncSession, test_org, test_user_member):
    """Test that a deactivated user is denied access immediately."""
    # Deactivate the user
    test_user_member.is_active = False
    await db_session.commit()

    token = create_access_token(test_user_member.id, test_org.id, test_user_member.role)
    headers = {"Authorization": f"Bearer {token}"}

    res = await client.get("/api/v1/leads", headers=headers)
    assert res.status_code == 401
    assert "not found, deactivated" in res.json()["error"]["message"].lower()


@pytest.mark.asyncio
async def test_expired_token_rejected(client: AsyncClient, test_user_owner, test_org):
    """Test that expired JWT access tokens are rejected with 401."""
    expired_token = create_access_token(
        test_user_owner.id,
        test_org.id,
        test_user_owner.role,
        expires_delta=timedelta(minutes=-10),  # expired 10 minutes ago
    )
    headers = {"Authorization": f"Bearer {expired_token}"}

    res = await client.get("/api/v1/auth/me", headers=headers)
    assert res.status_code == 401
    assert "expired" in res.json()["error"]["message"].lower()


@pytest.mark.asyncio
async def test_invalid_token_signature_rejected(client: AsyncClient, test_user_owner, test_org):
    """Test that tampered token signature is rejected with 401."""
    fake_token = jwt.encode(
        {"sub": test_user_owner.id, "org_id": test_org.id, "role": "OWNER", "type": "access"},
        "wrong_secret_key_12345678901234567890",
        algorithm="HS256",
    )
    headers = {"Authorization": f"Bearer {fake_token}"}

    res = await client.get("/api/v1/auth/me", headers=headers)
    assert res.status_code == 401
    assert "invalid authentication token" in res.json()["error"]["message"].lower()


@pytest.mark.asyncio
async def test_refresh_token_endpoint(client: AsyncClient, test_user_owner, test_org):
    """Test valid refresh token exchange for a fresh access token."""
    # 1. Login to get refresh token
    login_res = await client.post(
        "/api/v1/auth/login",
        json={"email": "owner@alpha.com", "password": "password123"},
    )
    assert login_res.status_code == 200
    refresh_token = login_res.json()["refresh_token"]

    # 2. Exchange refresh token
    refresh_res = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert refresh_res.status_code == 200
    new_data = refresh_res.json()
    assert "access_token" in new_data
    assert "refresh_token" in new_data


@pytest.mark.asyncio
async def test_access_token_cannot_be_used_as_refresh_token(client: AsyncClient, test_user_owner, test_org):
    """Test that an access token cannot be misused as a refresh token."""
    access_token = create_access_token(test_user_owner.id, test_org.id, test_user_owner.role)
    res = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": access_token},
    )
    assert res.status_code == 401
    assert "invalid refresh token type" in res.json()["error"]["message"].lower()


@pytest.mark.asyncio
async def test_duplicate_email_registration_in_same_org(client: AsyncClient, auth_headers_owner):
    """Test that inviting/creating a user with an already existing email in that org returns 409 Conflict."""
    payload = {
        "email": "owner@alpha.com",  # already exists in org-alpha
        "first_name": "Duplicate",
        "last_name": "User",
        "password": "Password123!",
        "role": "MEMBER",
    }
    res = await client.post("/api/v1/users", json=payload, headers=auth_headers_owner)
    assert res.status_code == 409
    assert "already exists" in res.json()["error"]["message"].lower()
