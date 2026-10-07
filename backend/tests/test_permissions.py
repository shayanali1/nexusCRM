import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_owner_can_manage_team(client: AsyncClient, auth_headers_owner):
    """Test OWNER role can invite team members."""
    payload = {
        "email": "new.rep@alpha.com",
        "first_name": "New",
        "last_name": "Representative",
        "password": "Password123!",
        "role": "MEMBER",
    }
    res = await client.post("/api/v1/users", json=payload, headers=auth_headers_owner)
    assert res.status_code == 201
    assert res.json()["email"] == "new.rep@alpha.com"


@pytest.mark.asyncio
async def test_member_cannot_manage_team(client: AsyncClient, auth_headers_member):
    """Test standard MEMBER role is forbidden from adding users."""
    payload = {
        "email": "unauthorized@alpha.com",
        "first_name": "Bad",
        "last_name": "Actor",
        "password": "Password123!",
        "role": "ADMIN",
    }
    res = await client.post("/api/v1/users", json=payload, headers=auth_headers_member)
    assert res.status_code == 403
