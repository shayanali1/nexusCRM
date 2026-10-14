import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.security import hash_password
from app.modules.companies.models import Company
from app.modules.contacts.models import Contact
from app.modules.deals.models import Deal
from app.modules.leads.models import Lead, LeadStatus
from app.modules.organizations.models import Organization
from app.modules.pipelines.models import Pipeline, PipelineStage
from app.modules.users.models import User
from app.core.security import create_access_token


@pytest.mark.asyncio
async def test_typed_lead_conversion_response_and_record_association(
    client: AsyncClient,
    test_org: Organization,
    auth_headers_owner: dict,
    db_session: AsyncSession,
    mock_celery_dispatch,
):
    """Test that lead conversion returns the typed LeadConvertResponse schema with all associated IDs."""
    # 1. Create a lead with inline contact and company
    create_payload = {
        "title": "Quantum AI Infrastructure",
        "contact_name": "Miles Dyson",
        "contact_email": "miles@cyberdyne.ai",
        "contact_phone": "+1 555-0155",
        "company_name": "Cyberdyne Systems",
        "source": "Website",
        "estimated_value": 85000.0,
    }
    create_res = await client.post("/api/v1/leads", json=create_payload, headers=auth_headers_owner)
    assert create_res.status_code == 201
    lead_data = create_res.json()
    lead_id = lead_data["id"]
    contact_id = lead_data["contact_id"]
    company_id = lead_data["company_id"]
    assert contact_id is not None
    assert company_id is not None

    # 2. Convert lead to deal
    convert_payload = {
        "deal_title": "Cyberdyne Quantum Scope Deal",
        "deal_value": 90000.0,
    }
    conv_res = await client.post(
        f"/api/v1/leads/{lead_id}/convert",
        json=convert_payload,
        headers=auth_headers_owner,
    )
    assert conv_res.status_code == 200
    conv_data = conv_res.json()

    # 3. Verify typed LeadConvertResponse fields
    assert conv_data["success"] is True
    assert conv_data["message"] == "Lead converted successfully to Deal."
    assert conv_data["lead_id"] == lead_id
    assert "deal_id" in conv_data
    assert conv_data["contact_id"] == contact_id
    assert conv_data["company_id"] == company_id

    # 4. Verify resulting Deal record in DB has expected associations
    deal_id = conv_data["deal_id"]
    deal_db = (await db_session.execute(select(Deal).where(Deal.id == deal_id))).scalar_one()
    assert deal_db.organization_id == test_org.id
    assert deal_db.contact_id == contact_id
    assert deal_db.company_id == company_id
    assert deal_db.title == "Cyberdyne Quantum Scope Deal"
    assert deal_db.value == 90000.0

    # 5. Verify lead status and conversion timestamps in DB
    lead_db = (await db_session.execute(select(Lead).where(Lead.id == lead_id))).scalar_one()
    assert lead_db.status == LeadStatus.QUALIFIED.value
    assert lead_db.converted_to_deal_id == deal_id
    assert lead_db.converted_at is not None


@pytest.mark.asyncio
async def test_lead_conversion_idempotency_preserves_records(
    client: AsyncClient,
    test_org: Organization,
    auth_headers_owner: dict,
    db_session: AsyncSession,
    mock_celery_dispatch,
):
    """Repeated conversion requests are rejected and do not create duplicate deals, contacts, or companies."""
    # Create lead with contact and company
    res = await client.post(
        "/api/v1/leads",
        json={
            "title": "Idempotent Conversion Test",
            "contact_name": "Kyle Reese",
            "contact_email": "kyle@resistance.org",
            "company_name": "Resistance HQ",
            "estimated_value": 25000.0,
        },
        headers=auth_headers_owner,
    )
    assert res.status_code == 201
    lead_id = res.json()["id"]

    # First conversion succeeds
    res_conv1 = await client.post(
        f"/api/v1/leads/{lead_id}/convert",
        json={"deal_title": "Primary Deal"},
        headers=auth_headers_owner,
    )
    assert res_conv1.status_code == 200

    deal_count_before = (await db_session.execute(select(func.count(Deal.id)).where(Deal.organization_id == test_org.id))).scalar()
    contact_count_before = (await db_session.execute(select(func.count(Contact.id)).where(Contact.organization_id == test_org.id))).scalar()
    company_count_before = (await db_session.execute(select(func.count(Company.id)).where(Company.organization_id == test_org.id))).scalar()

    # Second conversion attempt MUST be rejected with HTTP 400
    res_conv2 = await client.post(
        f"/api/v1/leads/{lead_id}/convert",
        json={"deal_title": "Duplicate Deal Attempt"},
        headers=auth_headers_owner,
    )
    assert res_conv2.status_code == 400
    assert "already been converted" in res_conv2.json()["error"]["message"]

    # Verify no duplicate deals, contacts, or companies were created
    deal_count_after = (await db_session.execute(select(func.count(Deal.id)).where(Deal.organization_id == test_org.id))).scalar()
    contact_count_after = (await db_session.execute(select(func.count(Contact.id)).where(Contact.organization_id == test_org.id))).scalar()
    company_count_after = (await db_session.execute(select(func.count(Company.id)).where(Company.organization_id == test_org.id))).scalar()

    assert deal_count_after == deal_count_before
    assert contact_count_after == contact_count_before
    assert company_count_after == company_count_before


@pytest.mark.asyncio
async def test_duplicate_lead_creation_by_email_conflict_409(
    client: AsyncClient,
    test_org: Organization,
    auth_headers_owner: dict,
    db_session: AsyncSession,
    mock_celery_dispatch,
):
    """Creating a lead with an existing contact email in the same organization returns HTTP 409 Conflict."""
    payload1 = {
        "title": "Initial Pipeline Lead",
        "contact_name": "Elena Rostova",
        "contact_email": "elena@novacorp.com",
        "company_name": "Nova Corp",
        "estimated_value": 40000.0,
    }
    res1 = await client.post("/api/v1/leads", json=payload1, headers=auth_headers_owner)
    assert res1.status_code == 201
    lead1_id = res1.json()["id"]

    # Duplicate attempt with identical email
    payload2 = {
        "title": "Duplicate Inquiry Lead",
        "contact_name": "Elena R.",
        "contact_email": "elena@novacorp.com",
        "company_name": "Nova Corporation",
        "estimated_value": 50000.0,
    }
    res2 = await client.post("/api/v1/leads", json=payload2, headers=auth_headers_owner)
    assert res2.status_code == 409
    assert res2.json()["error"]["code"] == "CONFLICT"
    assert "duplicate lead already exists" in res2.json()["error"]["message"]
    assert res2.json()["error"]["details"]["existing_lead_id"] == lead1_id

    # Duplicate attempt with case and whitespace variation
    payload3 = {
        "title": "Third Inquiry Lead",
        "contact_name": "Elena Rostova",
        "contact_email": "  ELENA@novacorp.com  ",
        "estimated_value": 30000.0,
    }
    res3 = await client.post("/api/v1/leads", json=payload3, headers=auth_headers_owner)
    assert res3.status_code == 409
    assert res3.json()["error"]["code"] == "CONFLICT"

    # Verify no second lead was created in database
    lead_count = (await db_session.execute(select(func.count(Lead.id)).where(Lead.organization_id == test_org.id))).scalar()
    assert lead_count == 1


@pytest.mark.asyncio
async def test_duplicate_lead_creation_by_phone_conflict_409(
    client: AsyncClient,
    test_org: Organization,
    auth_headers_owner: dict,
    db_session: AsyncSession,
    mock_celery_dispatch,
):
    """Creating a lead with an existing contact phone in the same organization returns HTTP 409 Conflict."""
    payload1 = {
        "title": "Direct Call Lead",
        "contact_name": "Marcus Wright",
        "contact_phone": "+1-555-4321",
        "company_name": "Marcus Logistics",
        "estimated_value": 35000.0,
    }
    res1 = await client.post("/api/v1/leads", json=payload1, headers=auth_headers_owner)
    assert res1.status_code == 201
    lead1_id = res1.json()["id"]

    # Duplicate attempt with identical phone
    payload2 = {
        "title": "Followup Call Lead",
        "contact_name": "Marcus W.",
        "contact_phone": "+1-555-4321",
        "estimated_value": 45000.0,
    }
    res2 = await client.post("/api/v1/leads", json=payload2, headers=auth_headers_owner)
    assert res2.status_code == 409
    assert res2.json()["error"]["code"] == "CONFLICT"
    assert res2.json()["error"]["details"]["existing_lead_id"] == lead1_id

    # Verify no second lead was created
    lead_count = (await db_session.execute(select(func.count(Lead.id)).where(Lead.organization_id == test_org.id))).scalar()
    assert lead_count == 1


@pytest.mark.asyncio
async def test_duplicate_lead_creation_by_contact_id_conflict_409(
    client: AsyncClient,
    test_org: Organization,
    auth_headers_owner: dict,
    db_session: AsyncSession,
    mock_celery_dispatch,
):
    """Creating a lead with an existing contact_id that already has a lead returns HTTP 409 Conflict."""
    contact = Contact(
        organization_id=test_org.id,
        first_name="John",
        last_name="Connor",
        email="john.connor@resistance.net",
    )
    db_session.add(contact)
    await db_session.commit()
    await db_session.refresh(contact)

    # First lead with contact_id succeeds
    res1 = await client.post(
        "/api/v1/leads",
        json={"title": "Resistance Lead 1", "contact_id": contact.id},
        headers=auth_headers_owner,
    )
    assert res1.status_code == 201
    lead1_id = res1.json()["id"]

    # Second lead with same contact_id returns 409 Conflict
    res2 = await client.post(
        "/api/v1/leads",
        json={"title": "Resistance Lead 2", "contact_id": contact.id},
        headers=auth_headers_owner,
    )
    assert res2.status_code == 409
    assert res2.json()["error"]["code"] == "CONFLICT"
    assert res2.json()["error"]["details"]["existing_lead_id"] == lead1_id

    # Verify only 1 lead in DB
    lead_count = (await db_session.execute(select(func.count(Lead.id)).where(Lead.organization_id == test_org.id))).scalar()
    assert lead_count == 1


@pytest.mark.asyncio
async def test_legitimate_distinct_leads_accepted(
    client: AsyncClient,
    test_org: Organization,
    auth_headers_owner: dict,
    db_session: AsyncSession,
    mock_celery_dispatch,
):
    """Legitimate leads with different contact identities are both accepted."""
    res1 = await client.post(
        "/api/v1/leads",
        json={"title": "Customer A Lead", "contact_name": "Alice Green", "contact_email": "alice@customer-a.com"},
        headers=auth_headers_owner,
    )
    assert res1.status_code == 201

    res2 = await client.post(
        "/api/v1/leads",
        json={"title": "Customer B Lead", "contact_name": "Bob Blue", "contact_email": "bob@customer-b.com"},
        headers=auth_headers_owner,
    )
    assert res2.status_code == 201

    lead_count = (await db_session.execute(select(func.count(Lead.id)).where(Lead.organization_id == test_org.id))).scalar()
    assert lead_count == 2


@pytest.mark.asyncio
async def test_duplicate_detection_scoped_to_organization(
    client: AsyncClient,
    test_org: Organization,
    auth_headers_owner: dict,
    db_session: AsyncSession,
    mock_celery_dispatch,
):
    """Duplicate detection never checks across organizations: Org B can create a lead with Org A's email."""
    # 1. Setup Organization Beta with an Owner user
    org_b = Organization(name="Organization Beta", slug="org-beta-dedup", is_active=True)
    db_session.add(org_b)
    await db_session.flush()

    user_b = User(
        organization_id=org_b.id,
        email="owner@beta-dedup.com",
        hashed_password=hash_password("password123"),
        first_name="Beta",
        last_name="Owner",
        role="OWNER",
        is_active=True,
    )
    db_session.add(user_b)
    await db_session.commit()

    token_b = create_access_token(user_b.id, org_b.id, user_b.role)
    auth_headers_b = {"Authorization": f"Bearer {token_b}"}

    shared_email = "prospect@globalenterprise.com"

    # 2. Create lead in Organization A
    res_a = await client.post(
        "/api/v1/leads",
        json={"title": "Org A Lead", "contact_name": "Global Prospect", "contact_email": shared_email},
        headers=auth_headers_owner,
    )
    assert res_a.status_code == 201

    # 3. Create lead in Organization B with the exact same contact_email -> MUST succeed
    res_b = await client.post(
        "/api/v1/leads",
        json={"title": "Org B Lead", "contact_name": "Global Prospect", "contact_email": shared_email},
        headers=auth_headers_b,
    )
    assert res_b.status_code == 201
    assert res_b.json()["organization_id"] == org_b.id

    # 4. Attempting duplicate in Organization A again returns 409 Conflict
    res_a_dup = await client.post(
        "/api/v1/leads",
        json={"title": "Org A Duplicate Lead", "contact_name": "Global Prospect", "contact_email": shared_email},
        headers=auth_headers_owner,
    )
    assert res_a_dup.status_code == 409
    assert res_a_dup.json()["error"]["code"] == "CONFLICT"


@pytest.mark.asyncio
async def test_missing_identity_information_does_not_reject_lead(
    client: AsyncClient,
    test_org: Organization,
    auth_headers_owner: dict,
    db_session: AsyncSession,
    mock_celery_dispatch,
):
    """Leads lacking identity fields (no email, phone, or contact_id) are not falsely rejected as duplicates."""
    payload1 = {
        "title": "General Inbound Web Lead",
        "company_name": "Walk-in Corp",
        "contact_name": "Anonymous Visitor",
        "estimated_value": 10000.0,
    }
    res1 = await client.post("/api/v1/leads", json=payload1, headers=auth_headers_owner)
    assert res1.status_code == 201

    # Identical title, company, and contact_name but without reliable identity fields (email/phone/contact_id)
    payload2 = {
        "title": "General Inbound Web Lead",
        "company_name": "Walk-in Corp",
        "contact_name": "Anonymous Visitor",
        "estimated_value": 10000.0,
    }
    res2 = await client.post("/api/v1/leads", json=payload2, headers=auth_headers_owner)
    assert res2.status_code == 201

    lead_count = (await db_session.execute(select(func.count(Lead.id)).where(Lead.organization_id == test_org.id))).scalar()
    assert lead_count == 2


@pytest.mark.asyncio
async def test_duplicate_lead_creation_cross_mode_existing_contact_vs_inline(
    client: AsyncClient,
    test_org: Organization,
    auth_headers_owner: dict,
    db_session: AsyncSession,
    mock_celery_dispatch,
):
    """An inline lead request matching the normalized email of a lead's linked contact returns HTTP 409."""
    # 1. Create a Contact in DB
    contact = Contact(
        organization_id=test_org.id,
        first_name="Evelyn",
        last_name="Cross",
        email="evelyn.cross@enterprise.io",
    )
    db_session.add(contact)
    await db_session.commit()
    await db_session.refresh(contact)

    # 2. Create Lead 1 linked to this contact (omitting inline contact_email)
    res1 = await client.post(
        "/api/v1/leads",
        json={"title": "Primary Linked Lead", "contact_id": contact.id},
        headers=auth_headers_owner,
    )
    assert res1.status_code == 201
    lead1_id = res1.json()["id"]

    # 3. Create Lead 2 inline with the same email (varying case and whitespace) without contact_id
    res2 = await client.post(
        "/api/v1/leads",
        json={
            "title": "Inbound Web Inquiry",
            "contact_name": "Evelyn Cross",
            "contact_email": "  EVELYN.CROSS@enterprise.io  ",
        },
        headers=auth_headers_owner,
    )
    assert res2.status_code == 409
    assert res2.json()["error"]["code"] == "CONFLICT"
    assert "duplicate lead already exists" in res2.json()["error"]["message"]
    assert res2.json()["error"]["details"]["existing_lead_id"] == lead1_id

    # Verify only 1 lead exists in DB
    lead_count = (await db_session.execute(select(func.count(Lead.id)).where(Lead.organization_id == test_org.id))).scalar()
    assert lead_count == 1


@pytest.mark.asyncio
async def test_lead_recreation_allowed_after_lead_deletion(
    client: AsyncClient,
    test_org: Organization,
    auth_headers_owner: dict,
    db_session: AsyncSession,
    mock_celery_dispatch,
):
    """Deleting a lead permits recreating a new lead with the same contact identity."""
    # 1. Create initial lead
    res1 = await client.post(
        "/api/v1/leads",
        json={"title": "Temporary Lead", "contact_name": "Ephemeral User", "contact_email": "ephemeral@lead.com"},
        headers=auth_headers_owner,
    )
    assert res1.status_code == 201
    lead1_id = res1.json()["id"]

    # 2. Delete the lead
    res_del = await client.delete(f"/api/v1/leads/{lead1_id}", headers=auth_headers_owner)
    assert res_del.status_code == 204

    # 3. Recreating a lead with the same email must succeed
    res2 = await client.post(
        "/api/v1/leads",
        json={"title": "Recreated Lead", "contact_name": "Ephemeral User", "contact_email": "ephemeral@lead.com"},
        headers=auth_headers_owner,
    )
    assert res2.status_code == 201
    lead2_id = res2.json()["id"]
    assert lead2_id != lead1_id

    # Verify database has exactly 1 active lead
    lead_count = (await db_session.execute(select(func.count(Lead.id)).where(Lead.organization_id == test_org.id))).scalar()
    assert lead_count == 1


@pytest.mark.asyncio
async def test_lead_conversion_with_null_relations_preserves_contract(
    client: AsyncClient,
    test_org: Organization,
    auth_headers_owner: dict,
    db_session: AsyncSession,
    mock_celery_dispatch,
):
    """Converting a lead without contact or company succeeds and explicitly returns null relation IDs."""
    # 1. Create bare lead
    res = await client.post(
        "/api/v1/leads",
        json={"title": "Unlinked Standalone Lead", "estimated_value": 42000.0},
        headers=auth_headers_owner,
    )
    assert res.status_code == 201
    lead_data = res.json()
    lead_id = lead_data["id"]
    assert lead_data["contact_id"] is None
    assert lead_data["company_id"] is None

    # 2. Convert bare lead to deal
    conv_res = await client.post(
        f"/api/v1/leads/{lead_id}/convert",
        json={"deal_title": "Standalone Deal"},
        headers=auth_headers_owner,
    )
    assert conv_res.status_code == 200
    conv_data = conv_res.json()
    assert conv_data["success"] is True
    assert conv_data["lead_id"] == lead_id
    assert conv_data["contact_id"] is None
    assert conv_data["company_id"] is None
    assert "deal_id" in conv_data
    deal_id = conv_data["deal_id"]

    # 3. Verify resulting Deal record in DB has null contact_id and company_id
    deal_db = (await db_session.execute(select(Deal).where(Deal.id == deal_id))).scalar_one()
    assert deal_db.contact_id is None
    assert deal_db.company_id is None
    assert deal_db.title == "Standalone Deal"
    assert deal_db.value == 42000.0
