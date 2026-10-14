import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from app.modules.companies.models import Company
from app.modules.contacts.models import Contact
from app.modules.deals.models import Deal
from app.modules.leads.models import Lead
from app.modules.organizations.models import Organization
from app.modules.pipelines.models import Pipeline, PipelineStage
from app.modules.users.models import User
from app.core.security import create_access_token, hash_password


@pytest.mark.asyncio
async def test_create_and_convert_lead(client: AsyncClient, auth_headers_owner, mock_celery_dispatch):
    """Test full customer lifecycle: lead creation -> qualification -> deal conversion."""
    # 1. Create Lead with inline contact & company
    create_payload = {
        "title": "FinTech Cloud Migration",
        "contact_name": "Sarah Connor",
        "contact_email": "sarah@skynet.ai",
        "contact_phone": "+1 555-0199",
        "company_name": "Cyberdyne Systems",
        "status": "NEW",
        "source": "Website",
        "estimated_value": 35000.0,
    }
    res = await client.post("/api/v1/leads", json=create_payload, headers=auth_headers_owner)
    assert res.status_code == 201
    lead = res.json()
    assert lead["title"] == "FinTech Cloud Migration"
    assert lead["contact_name"] == "Sarah Connor"
    assert lead["company_name"] == "Cyberdyne Systems"
    lead_id = lead["id"]

    # 2. Convert Lead to Deal
    convert_payload = {
        "deal_title": "Cyberdyne Cloud Scope Deal",
        "deal_value": 35000.0,
    }
    res_conv = await client.post(f"/api/v1/leads/{lead_id}/convert", json=convert_payload, headers=auth_headers_owner)
    assert res_conv.status_code == 200
    conv_data = res_conv.json()
    assert conv_data["success"] is True
    assert "deal_id" in conv_data

    # 3. Verify Deal exists in pipeline
    deal_id = conv_data["deal_id"]
    res_deal = await client.get(f"/api/v1/deals/{deal_id}", headers=auth_headers_owner)
    assert res_deal.status_code == 200
    assert res_deal.json()["title"] == "Cyberdyne Cloud Scope Deal"
    assert res_deal.json()["value"] == 35000.0


@pytest.mark.asyncio
async def test_lead_conversion_pipeline_and_stage_validation(
    client: AsyncClient,
    test_org: Organization,
    auth_headers_owner: dict,
    db_session,
    mock_celery_dispatch,
):
    """Test pipeline and stage validation during lead conversion."""
    # Create custom secondary pipeline with its own stage in the same organization
    custom_pipe = Pipeline(organization_id=test_org.id, name="Enterprise Pipeline", is_default=False)
    db_session.add(custom_pipe)
    await db_session.flush()

    custom_stage = PipelineStage(
        organization_id=test_org.id,
        pipeline_id=custom_pipe.id,
        name="Contract Review",
        order=1,
        win_probability=60,
    )
    db_session.add(custom_stage)

    # Get default pipeline and its stage
    def_pipe_stmt = select(Pipeline).where(Pipeline.organization_id == test_org.id, Pipeline.is_default.is_(True))
    default_pipe = (await db_session.execute(def_pipe_stmt)).scalars().first()
    def_stage_stmt = select(PipelineStage).where(PipelineStage.pipeline_id == default_pipe.id)
    default_stage = (await db_session.execute(def_stage_stmt)).scalars().first()
    await db_session.commit()

    # Create lead to test conversion
    lead_res = await client.post(
        "/api/v1/leads",
        json={"title": "Mismatched Stage Test Lead", "estimated_value": 50000.0},
        headers=auth_headers_owner,
    )
    assert lead_res.status_code == 201
    lead_id = lead_res.json()["id"]

    # 1. Reject mismatched pipeline & stage: default pipeline with custom_stage (from custom_pipe)
    res_mismatch = await client.post(
        f"/api/v1/leads/{lead_id}/convert",
        json={"pipeline_id": default_pipe.id, "stage_id": custom_stage.id},
        headers=auth_headers_owner,
    )
    assert res_mismatch.status_code == 400
    assert "does not belong to the selected pipeline" in res_mismatch.json()["error"]["message"]

    # 2. Supplying only custom pipeline selects the first stage of that pipeline
    res_custom = await client.post(
        f"/api/v1/leads/{lead_id}/convert",
        json={"pipeline_id": custom_pipe.id},
        headers=auth_headers_owner,
    )
    assert res_custom.status_code == 200
    deal_id = res_custom.json()["deal_id"]

    # Verify deal in database has custom pipeline and custom stage
    deal_db = (await db_session.execute(select(Deal).where(Deal.id == deal_id))).scalar_one()
    assert deal_db.pipeline_id == custom_pipe.id
    assert deal_db.stage_id == custom_stage.id


@pytest.mark.asyncio
async def test_lead_conversion_idempotency_prevents_duplicate_deals(
    client: AsyncClient,
    auth_headers_owner: dict,
    db_session,
    mock_celery_dispatch,
):
    """Converting an already-converted lead is rejected and produces no duplicate deals."""
    # Create lead
    lead_res = await client.post(
        "/api/v1/leads",
        json={"title": "Idempotent Conversion Lead", "estimated_value": 20000.0},
        headers=auth_headers_owner,
    )
    assert lead_res.status_code == 201
    lead_id = lead_res.json()["id"]

    # First conversion succeeds
    res_conv1 = await client.post(
        f"/api/v1/leads/{lead_id}/convert",
        json={"deal_title": "First Deal"},
        headers=auth_headers_owner,
    )
    assert res_conv1.status_code == 200
    deal_id_1 = res_conv1.json()["deal_id"]

    # Verify deal count for this lead in database is 1
    deal_count_stmt = select(func.count(Deal.id)).where(Deal.title == "First Deal")
    count_1 = (await db_session.execute(deal_count_stmt)).scalar()
    assert count_1 == 1

    # Second conversion attempt MUST be rejected
    res_conv2 = await client.post(
        f"/api/v1/leads/{lead_id}/convert",
        json={"deal_title": "Second Duplicate Deal"},
        headers=auth_headers_owner,
    )
    assert res_conv2.status_code == 400
    assert "already been converted" in res_conv2.json()["error"]["message"]

    # Verify database state: no second deal created, lead still points to original deal
    deal_count_all = select(func.count(Deal.id)).where(Deal.title.in_(["First Deal", "Second Duplicate Deal"]))
    count_2 = (await db_session.execute(deal_count_all)).scalar()
    assert count_2 == 1

    lead_db = (await db_session.execute(select(Lead).where(Lead.id == lead_id))).scalar_one()
    assert lead_db.converted_to_deal_id == deal_id_1


@pytest.mark.asyncio
async def test_company_deletion_preserves_contacts_with_null_company_id(
    client: AsyncClient,
    test_org: Organization,
    auth_headers_owner: dict,
    db_session,
):
    """Deleting a company must not delete its contacts; contacts must remain with company_id = NULL."""
    # 1. Create company
    comp_res = await client.post(
        "/api/v1/companies",
        json={"name": "Acme Holdings Corp", "domain": "acme.com"},
        headers=auth_headers_owner,
    )
    assert comp_res.status_code == 201
    comp_id = comp_res.json()["id"]

    # 2. Create two contacts linked to this company
    c1_res = await client.post(
        "/api/v1/contacts",
        json={"first_name": "Wile", "last_name": "Coyote", "company_id": comp_id, "email": "wile@acme.com"},
        headers=auth_headers_owner,
    )
    assert c1_res.status_code == 201
    c1_id = c1_res.json()["id"]

    c2_res = await client.post(
        "/api/v1/contacts",
        json={"first_name": "Road", "last_name": "Runner", "company_id": comp_id, "email": "runner@acme.com"},
        headers=auth_headers_owner,
    )
    assert c2_res.status_code == 201
    c2_id = c2_res.json()["id"]

    # 3. Delete company
    del_res = await client.delete(f"/api/v1/companies/{comp_id}", headers=auth_headers_owner)
    assert del_res.status_code == 204

    # 4. Verify company is gone
    get_comp = await client.get(f"/api/v1/companies/{comp_id}", headers=auth_headers_owner)
    assert get_comp.status_code == 404

    # 5. Verify both contacts STILL EXIST in the database with company_id = NULL
    contact1_db = (await db_session.execute(select(Contact).where(Contact.id == c1_id))).scalar_one_or_none()
    assert contact1_db is not None
    assert contact1_db.company_id is None
    assert contact1_db.first_name == "Wile"

    contact2_db = (await db_session.execute(select(Contact).where(Contact.id == c2_id))).scalar_one_or_none()
    assert contact2_db is not None
    assert contact2_db.company_id is None
    assert contact2_db.first_name == "Road"


@pytest.mark.asyncio
async def test_contact_disassociation_does_not_delete_contact(
    client: AsyncClient,
    test_org: Organization,
    auth_headers_owner: dict,
    db_session,
):
    """Setting company_id = None on a contact disassociates it without deleting the contact."""
    # 1. Create company and contact
    comp_res = await client.post(
        "/api/v1/companies",
        json={"name": "Beta Labs", "domain": "betalabs.io"},
        headers=auth_headers_owner,
    )
    assert comp_res.status_code == 201
    comp_id = comp_res.json()["id"]

    c_res = await client.post(
        "/api/v1/contacts",
        json={"first_name": "Ada", "last_name": "Lovelace", "company_id": comp_id, "email": "ada@betalabs.io"},
        headers=auth_headers_owner,
    )
    assert c_res.status_code == 201
    c_id = c_res.json()["id"]

    # 2. Disassociate contact by setting company_id to None
    patch_res = await client.patch(
        f"/api/v1/contacts/{c_id}",
        json={"company_id": None},
        headers=auth_headers_owner,
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["company_id"] is None

    # 3. Verify contact is not deleted and company_id is None
    contact_db = (await db_session.execute(select(Contact).where(Contact.id == c_id))).scalar_one_or_none()
    assert contact_db is not None
    assert contact_db.company_id is None
    assert contact_db.first_name == "Ada"


@pytest.mark.asyncio
async def test_legitimate_same_org_lead_and_contact_lifecycle(
    client: AsyncClient,
    test_org: Organization,
    test_user_member: User,
    auth_headers_owner: dict,
    db_session,
    mock_celery_dispatch,
):
    """Valid same-org relations across company, contact, assigned user and conversion succeed."""
    # 1. Create company
    comp_res = await client.post(
        "/api/v1/companies",
        json={"name": "Nexus Global", "domain": "nexusglobal.com"},
        headers=auth_headers_owner,
    )
    assert comp_res.status_code == 201
    comp_id = comp_res.json()["id"]

    # 2. Create contact referencing valid company
    contact_res = await client.post(
        "/api/v1/contacts",
        json={"first_name": "Grace", "last_name": "Hopper", "company_id": comp_id, "email": "grace@nexusglobal.com"},
        headers=auth_headers_owner,
    )
    assert contact_res.status_code == 201
    contact_id = contact_res.json()["id"]

    # 3. Create lead referencing valid company, contact, and assigned user
    lead_res = await client.post(
        "/api/v1/leads",
        json={
            "title": "Compiler Optimization Lead",
            "company_id": comp_id,
            "contact_id": contact_id,
            "assigned_to_id": test_user_member.id,
            "estimated_value": 75000.0,
        },
        headers=auth_headers_owner,
    )
    assert lead_res.status_code == 201
    lead_data = lead_res.json()
    assert lead_data["company_id"] == comp_id
    assert lead_data["contact_id"] == contact_id
    assert lead_data["assigned_to_id"] == test_user_member.id
    lead_id = lead_data["id"]

    # 4. Update lead with same-org relationships preserved
    update_res = await client.patch(
        f"/api/v1/leads/{lead_id}",
        json={"notes": "Priority customer account."},
        headers=auth_headers_owner,
    )
    assert update_res.status_code == 200
    assert update_res.json()["notes"] == "Priority customer account."

    # 5. Convert lead
    conv_res = await client.post(
        f"/api/v1/leads/{lead_id}/convert",
        json={"deal_title": "Nexus Enterprise Deal"},
        headers=auth_headers_owner,
    )
    assert conv_res.status_code == 200
    deal_id = conv_res.json()["deal_id"]

    deal_db = (await db_session.execute(select(Deal).where(Deal.id == deal_id))).scalar_one()
    assert deal_db.company_id == comp_id
    assert deal_db.contact_id == contact_id
    assert deal_db.assigned_to_id == test_user_member.id


@pytest.mark.asyncio
async def test_lead_assignment_rejects_inactive_user(
    client: AsyncClient,
    test_org: Organization,
    test_user_member: User,
    auth_headers_owner: dict,
    db_session,
    mock_celery_dispatch,
):
    """Assigning an inactive user from the same organization to a lead is rejected on create and update."""
    # Create an inactive user in test_org
    inactive_user = User(
        organization_id=test_org.id,
        email="inactive.staff@alpha.com",
        hashed_password=hash_password("password123"),
        first_name="Inactive",
        last_name="Staff",
        role="MEMBER",
        is_active=False,
        is_verified=True,
    )
    db_session.add(inactive_user)
    await db_session.commit()

    # 1. Reject lead creation with inactive user
    create_res = await client.post(
        "/api/v1/leads",
        json={"title": "Inactive Assignee Lead", "assigned_to_id": inactive_user.id},
        headers=auth_headers_owner,
    )
    assert create_res.status_code == 404
    assert "User not found" in create_res.json()["error"]["message"]

    # Verify lead was not persisted in database
    chk = await db_session.execute(select(Lead).where(Lead.title == "Inactive Assignee Lead"))
    assert chk.scalar_one_or_none() is None

    # 2. Create legitimate lead assigned to active member
    legit_res = await client.post(
        "/api/v1/leads",
        json={"title": "Active Member Lead", "assigned_to_id": test_user_member.id},
        headers=auth_headers_owner,
    )
    assert legit_res.status_code == 201
    lead_id = legit_res.json()["id"]

    # 3. Reject lead update with inactive user
    patch_res = await client.patch(
        f"/api/v1/leads/{lead_id}",
        json={"assigned_to_id": inactive_user.id},
        headers=auth_headers_owner,
    )
    assert patch_res.status_code == 404
    assert "User not found" in patch_res.json()["error"]["message"]

    # 4. Verify persisted lead state remains unchanged after rejected update
    lead_db = (await db_session.execute(select(Lead).where(Lead.id == lead_id))).scalar_one()
    assert lead_db.assigned_to_id == test_user_member.id
    assert lead_db.title == "Active Member Lead"


@pytest.mark.asyncio
async def test_lead_relationship_disassociation(
    client: AsyncClient,
    test_org: Organization,
    test_user_member: User,
    auth_headers_owner: dict,
    db_session,
    mock_celery_dispatch,
):
    """Lead updates can explicitly set company_id, contact_id, and assigned_to_id to null."""
    # 1. Create company and contact
    comp_res = await client.post(
        "/api/v1/companies",
        json={"name": "Disassociate Tech", "domain": "disassociate.tech"},
        headers=auth_headers_owner,
    )
    assert comp_res.status_code == 201
    comp_id = comp_res.json()["id"]

    contact_res = await client.post(
        "/api/v1/contacts",
        json={"first_name": "Alan", "last_name": "Turing", "company_id": comp_id, "email": "alan@disassociate.tech"},
        headers=auth_headers_owner,
    )
    assert contact_res.status_code == 201
    contact_id = contact_res.json()["id"]

    # 2. Create lead referencing all three relationships
    lead_res = await client.post(
        "/api/v1/leads",
        json={
            "title": "Fully Linked Lead",
            "company_id": comp_id,
            "contact_id": contact_id,
            "assigned_to_id": test_user_member.id,
        },
        headers=auth_headers_owner,
    )
    assert lead_res.status_code == 201
    lead_id = lead_res.json()["id"]

    # 3. Disassociate company_id by setting to null
    patch_comp = await client.patch(
        f"/api/v1/leads/{lead_id}",
        json={"company_id": None},
        headers=auth_headers_owner,
    )
    assert patch_comp.status_code == 200
    assert patch_comp.json()["company_id"] is None
    assert patch_comp.json()["contact_id"] == contact_id
    assert patch_comp.json()["assigned_to_id"] == test_user_member.id

    # 4. Disassociate contact_id by setting to null
    patch_cont = await client.patch(
        f"/api/v1/leads/{lead_id}",
        json={"contact_id": None},
        headers=auth_headers_owner,
    )
    assert patch_cont.status_code == 200
    assert patch_cont.json()["company_id"] is None
    assert patch_cont.json()["contact_id"] is None
    assert patch_cont.json()["assigned_to_id"] == test_user_member.id

    # 5. Disassociate assigned_to_id by setting to null
    patch_user = await client.patch(
        f"/api/v1/leads/{lead_id}",
        json={"assigned_to_id": None},
        headers=auth_headers_owner,
    )
    assert patch_user.status_code == 200
    assert patch_user.json()["company_id"] is None
    assert patch_user.json()["contact_id"] is None
    assert patch_user.json()["assigned_to_id"] is None

    # 6. Verify lead remains persisted in database with all three relationship fields cleared
    lead_db = (await db_session.execute(select(Lead).where(Lead.id == lead_id))).scalar_one_or_none()
    assert lead_db is not None
    assert lead_db.title == "Fully Linked Lead"
    assert lead_db.company_id is None
    assert lead_db.contact_id is None
    assert lead_db.assigned_to_id is None


@pytest.mark.asyncio
async def test_lead_conversion_fails_when_org_has_no_pipeline(
    client: AsyncClient,
    db_session,
    mock_celery_dispatch,
):
    """Converting a lead fails with 400 when organization has no sales pipeline configured."""
    # Create isolated organization with no pipelines
    org_no_pipe = Organization(name="No Pipeline Org", slug="no-pipeline-org", is_active=True)
    db_session.add(org_no_pipe)
    await db_session.flush()

    user = User(
        organization_id=org_no_pipe.id,
        email="owner@nopipeline.com",
        hashed_password=hash_password("password123"),
        first_name="NoPipe",
        last_name="Owner",
        role="OWNER",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()

    token = create_access_token(user.id, org_no_pipe.id, user.role)
    auth_headers = {"Authorization": f"Bearer {token}"}

    # Create lead in this organization
    res_lead = await client.post(
        "/api/v1/leads",
        json={"title": "Lead With No Org Pipeline"},
        headers=auth_headers,
    )
    assert res_lead.status_code == 201
    lead_id = res_lead.json()["id"]

    # Attempt conversion without specifying pipeline (defaults to org pipeline, which does not exist)
    res_conv = await client.post(
        f"/api/v1/leads/{lead_id}/convert",
        json={"deal_title": "Impossible Deal"},
        headers=auth_headers,
    )
    assert res_conv.status_code == 400
    assert "No sales pipeline configured" in res_conv.json()["error"]["message"]

    # Verify no deal was created in this organization
    deal_count = (await db_session.execute(select(func.count(Deal.id)).where(Deal.organization_id == org_no_pipe.id))).scalar()
    assert deal_count == 0

    # Verify lead was not marked as converted
    lead_db = (await db_session.execute(select(Lead).where(Lead.id == lead_id))).scalar_one()
    assert lead_db.converted_to_deal_id is None
    assert lead_db.converted_at is None
    assert lead_db.status != "QUALIFIED"


@pytest.mark.asyncio
async def test_lead_conversion_fails_when_pipeline_has_no_stages(
    client: AsyncClient,
    test_org: Organization,
    auth_headers_owner: dict,
    db_session,
    mock_celery_dispatch,
):
    """Converting a lead fails with 400 when the selected pipeline has no stages configured."""
    # Create pipeline with no stages in test_org
    stageless_pipe = Pipeline(organization_id=test_org.id, name="Stageless Pipeline", is_default=False)
    db_session.add(stageless_pipe)
    await db_session.commit()

    # Create lead in test_org
    res_lead = await client.post(
        "/api/v1/leads",
        json={"title": "Lead For Stageless Pipeline"},
        headers=auth_headers_owner,
    )
    assert res_lead.status_code == 201
    lead_id = res_lead.json()["id"]

    # Record initial deal count for test_org
    initial_deal_count = (await db_session.execute(select(func.count(Deal.id)).where(Deal.organization_id == test_org.id))).scalar()

    # Attempt conversion specifying the stageless pipeline
    res_conv = await client.post(
        f"/api/v1/leads/{lead_id}/convert",
        json={"pipeline_id": stageless_pipe.id, "deal_title": "Stageless Deal"},
        headers=auth_headers_owner,
    )
    assert res_conv.status_code == 400
    assert "Pipeline has no stages configured" in res_conv.json()["error"]["message"]

    # Verify no deal was created
    final_deal_count = (await db_session.execute(select(func.count(Deal.id)).where(Deal.organization_id == test_org.id))).scalar()
    assert final_deal_count == initial_deal_count

    pipe_deal_count = (await db_session.execute(select(func.count(Deal.id)).where(Deal.pipeline_id == stageless_pipe.id))).scalar()
    assert pipe_deal_count == 0

    # Verify lead was not marked as converted
    lead_db = (await db_session.execute(select(Lead).where(Lead.id == lead_id))).scalar_one()
    assert lead_db.converted_to_deal_id is None
    assert lead_db.converted_at is None
    assert lead_db.status != "QUALIFIED"
