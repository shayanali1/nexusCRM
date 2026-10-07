from datetime import datetime, timezone
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.automation.models import AutomationRule
from app.modules.companies.models import Company
from app.modules.contacts.models import Contact
from app.modules.deals.models import Deal
from app.modules.notifications.models import Notification
from app.modules.organizations.models import Organization
from app.modules.pipelines.models import Pipeline, PipelineStage
from app.modules.tasks.models import Task
from app.modules.users.models import User
from app.core.security import hash_password


@pytest_asyncio.fixture(scope="function")
async def foreign_org_and_entities(db_session: AsyncSession):
    """Setup Organization Beta with its own companies, contacts, deals, tasks, and automations."""
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

    company_b = Company(organization_id=org_b.id, name="Beta Confidential Corp")
    db_session.add(company_b)
    await db_session.flush()

    contact_b = Contact(
        organization_id=org_b.id,
        company_id=company_b.id,
        first_name="Secret",
        last_name="Agent",
        email="agent@beta.com",
    )
    db_session.add(contact_b)
    await db_session.flush()

    pipe_b = Pipeline(organization_id=org_b.id, name="Beta Pipeline", is_default=True)
    db_session.add(pipe_b)
    await db_session.flush()

    stage_b = PipelineStage(organization_id=org_b.id, pipeline_id=pipe_b.id, name="Discovery", order=1, win_probability=10)
    db_session.add(stage_b)
    await db_session.flush()

    deal_b = Deal(
        organization_id=org_b.id,
        pipeline_id=pipe_b.id,
        stage_id=stage_b.id,
        contact_id=contact_b.id,
        company_id=company_b.id,
        title="Beta Secret Deal $500k",
        value=500000.0,
    )
    db_session.add(deal_b)
    await db_session.flush()

    task_b = Task(
        organization_id=org_b.id,
        title="Beta Secret Followup",
        due_date=datetime.now(timezone.utc),
    )
    db_session.add(task_b)
    await db_session.flush()

    rule_b = AutomationRule(
        organization_id=org_b.id,
        name="Beta Rule",
        event_trigger="lead.created",
    )
    db_session.add(rule_b)
    await db_session.flush()

    notif_b = Notification(
        organization_id=org_b.id,
        user_id=user_b.id,
        title="Beta Secret Alert",
        message="Sensitive org B info",
    )
    db_session.add(notif_b)
    await db_session.commit()

    return {
        "org_b": org_b,
        "user_b": user_b,
        "company_b": company_b,
        "contact_b": contact_b,
        "deal_b": deal_b,
        "task_b": task_b,
        "rule_b": rule_b,
        "notif_b": notif_b,
    }


@pytest.mark.asyncio
async def test_cross_tenant_contact_isolation(client: AsyncClient, auth_headers_owner, foreign_org_and_entities):
    """Org A cannot view, update, or delete Org B contacts."""
    contact_id = foreign_org_and_entities["contact_b"].id

    res_get = await client.get(f"/api/v1/contacts/{contact_id}", headers=auth_headers_owner)
    assert res_get.status_code == 404

    res_patch = await client.patch(f"/api/v1/contacts/{contact_id}", json={"first_name": "Hacked"}, headers=auth_headers_owner)
    assert res_patch.status_code == 404

    res_del = await client.delete(f"/api/v1/contacts/{contact_id}", headers=auth_headers_owner)
    assert res_del.status_code == 404


@pytest.mark.asyncio
async def test_cross_tenant_company_isolation(client: AsyncClient, auth_headers_owner, foreign_org_and_entities):
    """Org A cannot view, update, or delete Org B companies."""
    company_id = foreign_org_and_entities["company_b"].id

    res_get = await client.get(f"/api/v1/companies/{company_id}", headers=auth_headers_owner)
    assert res_get.status_code == 404

    res_patch = await client.patch(f"/api/v1/companies/{company_id}", json={"name": "Hacked Corp"}, headers=auth_headers_owner)
    assert res_patch.status_code == 404

    res_del = await client.delete(f"/api/v1/companies/{company_id}", headers=auth_headers_owner)
    assert res_del.status_code == 404


@pytest.mark.asyncio
async def test_cross_tenant_deal_isolation(client: AsyncClient, auth_headers_owner, foreign_org_and_entities):
    """Org A cannot view, update, or delete Org B deals."""
    deal_id = foreign_org_and_entities["deal_b"].id

    res_get = await client.get(f"/api/v1/deals/{deal_id}", headers=auth_headers_owner)
    assert res_get.status_code == 404

    res_patch = await client.patch(f"/api/v1/deals/{deal_id}", json={"value": 1.0}, headers=auth_headers_owner)
    assert res_patch.status_code == 404

    res_del = await client.delete(f"/api/v1/deals/{deal_id}", headers=auth_headers_owner)
    assert res_del.status_code == 404


@pytest.mark.asyncio
async def test_cross_tenant_task_isolation(client: AsyncClient, auth_headers_owner, foreign_org_and_entities):
    """Org A cannot view, complete, or delete Org B tasks."""
    task_id = foreign_org_and_entities["task_b"].id

    res_complete = await client.post(f"/api/v1/tasks/{task_id}/complete", headers=auth_headers_owner)
    assert res_complete.status_code == 404

    res_patch = await client.patch(f"/api/v1/tasks/{task_id}", json={"title": "Hacked"}, headers=auth_headers_owner)
    assert res_patch.status_code == 404

    res_del = await client.delete(f"/api/v1/tasks/{task_id}", headers=auth_headers_owner)
    assert res_del.status_code == 404


@pytest.mark.asyncio
async def test_cross_tenant_automation_isolation(client: AsyncClient, auth_headers_owner, foreign_org_and_entities):
    """Org A cannot update Org B automation rules."""
    rule_id = foreign_org_and_entities["rule_b"].id

    res_patch = await client.patch(f"/api/v1/automation/rules/{rule_id}", json={"name": "Hacked Rule"}, headers=auth_headers_owner)
    assert res_patch.status_code == 404


@pytest.mark.asyncio
async def test_cross_tenant_reports_isolation(client: AsyncClient, auth_headers_owner, foreign_org_and_entities):
    """Org A's dashboard overview never includes Org B deals or values."""
    res = await client.get("/api/v1/reports/dashboard", headers=auth_headers_owner)
    assert res.status_code == 200
    data = res.json()
    # Org B has a $500,000 deal; Org A's pipeline value must NOT include it
    assert data["kpis"]["pipeline_value"] < 500000.0
