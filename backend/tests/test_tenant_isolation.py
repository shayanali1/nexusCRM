import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.security import create_access_token, hash_password
from app.modules.leads.models import Lead
from app.modules.organizations.models import Organization
from app.modules.users.models import User


@pytest.mark.asyncio
async def test_strict_tenant_isolation(client: AsyncClient, db_session: AsyncSession, auth_headers_owner, test_org):
    """Test that Organization A user cannot access, modify, or view Organization B records."""
    # 1. Create Organization B with its own lead
    org_b = Organization(name="Org Beta", slug="org-beta", is_active=True)
    db_session.add(org_b)
    await db_session.flush()

    user_b = User(
        organization_id=org_b.id,
        email="owner@beta.com",
        hashed_password=hash_password("password123"),
        first_name="Beta",
        last_name="Owner",
        role="OWNER",
        is_active=True,
    )
    db_session.add(user_b)
    await db_session.flush()

    lead_b = Lead(
        organization_id=org_b.id,
        title="Confidential Lead for Org Beta",
        status="NEW",
        source="Cold Outreach",
        estimated_value=100000.0,
    )
    db_session.add(lead_b)
    await db_session.commit()

    # 2. Organization A user queries leads list — should NOT see Org B's lead
    res_list = await client.get("/api/v1/leads", headers=auth_headers_owner)
    assert res_list.status_code == 200
    leads = res_list.json()
    assert all(l["id"] != lead_b.id for l in leads)

    # 3. Organization A user directly attempts to GET Org B's lead by ID — MUST return 404 (or 403)
    res_get = await client.get(f"/api/v1/leads/{lead_b.id}", headers=auth_headers_owner)
    assert res_get.status_code == 404

    # 4. Organization A user attempts to UPDATE Org B's lead — MUST return 404
    res_patch = await client.patch(
        f"/api/v1/leads/{lead_b.id}",
        json={"title": "Hacked Title"},
        headers=auth_headers_owner,
    )
    assert res_patch.status_code == 404

    # 5. Organization A user attempts to DELETE Org B's lead — MUST return 404
    res_del = await client.delete(f"/api/v1/leads/{lead_b.id}", headers=auth_headers_owner)
    assert res_del.status_code == 404
