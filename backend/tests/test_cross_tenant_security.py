from datetime import datetime, timezone
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.automation.models import AutomationRule
from app.modules.companies.models import Company
from app.modules.contacts.models import Contact
from app.modules.deals.models import Deal
from app.modules.leads.models import Lead
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
        "pipe_b": pipe_b,
        "stage_b": stage_b,
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


@pytest.mark.asyncio
async def test_cross_tenant_contact_relationship_injection_prevented(
    client: AsyncClient,
    auth_headers_owner,
    foreign_org_and_entities,
    db_session: AsyncSession,
):
    """Creating or updating a Contact with a foreign organization's company ID is strictly rejected."""
    foreign_company_id = foreign_org_and_entities["company_b"].id

    # 1. Reject creation with foreign company_id
    create_payload = {
        "first_name": "Infiltrator",
        "last_name": "Spy",
        "email": "spy@alpha.com",
        "company_id": foreign_company_id,
    }
    res_create = await client.post("/api/v1/contacts", json=create_payload, headers=auth_headers_owner)
    assert res_create.status_code == 404
    assert "Company not found" in res_create.json()["error"]["message"]

    # Verify contact was not persisted in database
    chk = await db_session.execute(select(Contact).where(Contact.email == "spy@alpha.com"))
    assert chk.scalar_one_or_none() is None

    # 2. Create legitimate contact in Org A
    legit_payload = {
        "first_name": "John",
        "last_name": "Doe",
        "email": "john.doe@alpha.com",
    }
    res_legit = await client.post("/api/v1/contacts", json=legit_payload, headers=auth_headers_owner)
    assert res_legit.status_code == 201
    contact_id = res_legit.json()["id"]

    # 3. Reject update referencing foreign company_id
    res_patch = await client.patch(
        f"/api/v1/contacts/{contact_id}",
        json={"company_id": foreign_company_id},
        headers=auth_headers_owner,
    )
    assert res_patch.status_code == 404
    assert "Company not found" in res_patch.json()["error"]["message"]

    # Verify contact's company_id in database is unchanged (still None)
    contact_db = (await db_session.execute(select(Contact).where(Contact.id == contact_id))).scalar_one()
    assert contact_db.company_id is None

    # Explicitly verify Organization B's foreign company and its existing contacts remain unchanged
    foreign_org_b_id = foreign_org_and_entities["org_b"].id
    foreign_contact_id = foreign_org_and_entities["contact_b"].id

    company_b_db = (await db_session.execute(select(Company).where(Company.id == foreign_company_id))).scalar_one()
    assert company_b_db.organization_id == foreign_org_b_id
    assert company_b_db.name == "Beta Confidential Corp"

    contacts_b_db = (await db_session.execute(select(Contact).where(Contact.company_id == foreign_company_id))).scalars().all()
    assert len(contacts_b_db) == 1
    assert contacts_b_db[0].id == foreign_contact_id
    assert contacts_b_db[0].organization_id == foreign_org_b_id
    assert contacts_b_db[0].email == "agent@beta.com"


@pytest.mark.asyncio
async def test_cross_tenant_lead_relationship_injection_prevented(
    client: AsyncClient,
    auth_headers_owner,
    foreign_org_and_entities,
    db_session: AsyncSession,
    mock_celery_dispatch,
):
    """Creating or updating a Lead with foreign-tenant contact, company, or user is strictly rejected."""
    foreign_company_id = foreign_org_and_entities["company_b"].id
    foreign_contact_id = foreign_org_and_entities["contact_b"].id
    foreign_user_id = foreign_org_and_entities["user_b"].id

    # 1. Reject create with foreign company_id
    res_comp = await client.post(
        "/api/v1/leads",
        json={"title": "Hack Company", "company_id": foreign_company_id},
        headers=auth_headers_owner,
    )
    assert res_comp.status_code == 404
    assert "Company not found" in res_comp.json()["error"]["message"]

    # 2. Reject create with foreign contact_id
    res_cont = await client.post(
        "/api/v1/leads",
        json={"title": "Hack Contact", "contact_id": foreign_contact_id},
        headers=auth_headers_owner,
    )
    assert res_cont.status_code == 404
    assert "Contact not found" in res_cont.json()["error"]["message"]

    # 3. Reject create with foreign assigned_to_id
    res_user = await client.post(
        "/api/v1/leads",
        json={"title": "Hack User", "assigned_to_id": foreign_user_id},
        headers=auth_headers_owner,
    )
    assert res_user.status_code == 404
    assert "User not found" in res_user.json()["error"]["message"]

    # 4. Create legitimate lead in Org A
    res_legit = await client.post(
        "/api/v1/leads",
        json={"title": "Valid Alpha Lead", "source": "Referral"},
        headers=auth_headers_owner,
    )
    assert res_legit.status_code == 201
    lead_id = res_legit.json()["id"]
    initial_assigned_to = res_legit.json()["assigned_to_id"]

    # 5. Reject patch with foreign relationships
    res_patch_comp = await client.patch(
        f"/api/v1/leads/{lead_id}",
        json={"company_id": foreign_company_id},
        headers=auth_headers_owner,
    )
    assert res_patch_comp.status_code == 404
    assert "Company not found" in res_patch_comp.json()["error"]["message"]

    res_patch_cont = await client.patch(
        f"/api/v1/leads/{lead_id}",
        json={"contact_id": foreign_contact_id},
        headers=auth_headers_owner,
    )
    assert res_patch_cont.status_code == 404
    assert "Contact not found" in res_patch_cont.json()["error"]["message"]

    res_patch_user = await client.patch(
        f"/api/v1/leads/{lead_id}",
        json={"assigned_to_id": foreign_user_id},
        headers=auth_headers_owner,
    )
    assert res_patch_user.status_code == 404
    assert "User not found" in res_patch_user.json()["error"]["message"]

    # Verify lead in DB remains uncorrupted
    lead_db = (await db_session.execute(select(Lead).where(Lead.id == lead_id))).scalar_one()
    assert lead_db.company_id is None
    assert lead_db.contact_id is None
    assert lead_db.assigned_to_id == initial_assigned_to
    assert lead_db.assigned_to_id != foreign_user_id


@pytest.mark.asyncio
async def test_cross_tenant_lead_conversion_injection_prevented(
    client: AsyncClient,
    auth_headers_owner,
    foreign_org_and_entities,
    db_session: AsyncSession,
    mock_celery_dispatch,
):
    """Converting a lead using a foreign tenant's pipeline or stage is strictly rejected."""
    foreign_pipe_id = foreign_org_and_entities["pipe_b"].id
    foreign_stage_id = foreign_org_and_entities["stage_b"].id
    org_b_id = foreign_org_and_entities["org_b"].id

    # Create legitimate lead in Org A
    res_lead = await client.post(
        "/api/v1/leads",
        json={"title": "Alpha Lead For Conversion", "estimated_value": 12000.0},
        headers=auth_headers_owner,
    )
    assert res_lead.status_code == 201
    lead_id = res_lead.json()["id"]

    # Record initial deal counts for both organizations
    lead_org_a_id = (await db_session.execute(select(Lead.organization_id).where(Lead.id == lead_id))).scalar()
    initial_deals_org_a = (await db_session.execute(select(func.count(Deal.id)).where(Deal.organization_id == lead_org_a_id))).scalar()
    initial_deals_org_b = (await db_session.execute(select(func.count(Deal.id)).where(Deal.organization_id == org_b_id))).scalar()

    # 1. Attempt conversion with foreign pipeline
    res_conv_pipe = await client.post(
        f"/api/v1/leads/{lead_id}/convert",
        json={"pipeline_id": foreign_pipe_id},
        headers=auth_headers_owner,
    )
    assert res_conv_pipe.status_code == 404
    assert "Pipeline not found" in res_conv_pipe.json()["error"]["message"]

    # 2. Attempt conversion with foreign stage
    res_conv_stage = await client.post(
        f"/api/v1/leads/{lead_id}/convert",
        json={"stage_id": foreign_stage_id},
        headers=auth_headers_owner,
    )
    assert res_conv_stage.status_code == 404
    assert "Pipeline stage not found" in res_conv_stage.json()["error"]["message"]

    # Verify lead was NOT converted
    lead_db = (await db_session.execute(select(Lead).where(Lead.id == lead_id))).scalar_one()
    assert lead_db.converted_to_deal_id is None
    assert lead_db.converted_at is None
    assert lead_db.status != "QUALIFIED"

    # Verify no additional deal was created in either organization
    final_deals_org_a = (await db_session.execute(select(func.count(Deal.id)).where(Deal.organization_id == lead_org_a_id))).scalar()
    final_deals_org_b = (await db_session.execute(select(func.count(Deal.id)).where(Deal.organization_id == org_b_id))).scalar()
    assert final_deals_org_a == initial_deals_org_a
    assert final_deals_org_b == initial_deals_org_b
