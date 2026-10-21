import pytest
import pytest_asyncio
from datetime import datetime, timezone, timedelta
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.security import create_access_token, hash_password
from app.modules.audit.models import AuditLog
from app.modules.companies.models import Company
from app.modules.contacts.models import Contact
from app.modules.deals.models import Deal
from app.modules.leads.models import Lead
from app.modules.organizations.models import Organization
from app.modules.pipelines.models import Pipeline, PipelineStage
from app.modules.users.models import User


@pytest_asyncio.fixture(scope="function")
async def test_user_manager(db_session: AsyncSession, test_org: Organization) -> User:
    """Create test Manager user in Organization A."""
    user = User(
        organization_id=test_org.id,
        email="manager@alpha.com",
        hashed_password=hash_password("password123"),
        first_name="Mary",
        last_name="Manager",
        role="MANAGER",
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def auth_headers_manager(test_user_manager: User, test_org: Organization) -> dict:
    token = create_access_token(test_user_manager.id, test_org.id, test_user_manager.role)
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture(scope="function")
async def seed_audit_test_data(
    db_session: AsyncSession,
    test_org: Organization,
    test_user_owner: User,
    test_user_member: User,
):
    """Seed comprehensive test entities and audit logs across Org A and foreign Org B."""
    base_time = datetime(2026, 7, 1, 10, 0, 0, tzinfo=timezone.utc)

    # 1. Org A entities
    lead_a = Lead(
        organization_id=test_org.id,
        title="Alpha Enterprise Lead",
        assigned_to_id=test_user_owner.id,
        status="NEW",
    )
    db_session.add(lead_a)

    company_a = Company(
        organization_id=test_org.id,
        name="Alpha Logistics",
    )
    db_session.add(company_a)
    await db_session.flush()

    contact_a = Contact(
        organization_id=test_org.id,
        company_id=company_a.id,
        first_name="Alice",
        last_name="Alpha",
        email="alice@alpha.com",
    )
    db_session.add(contact_a)

    pipe_a = Pipeline(
        organization_id=test_org.id,
        name="Alpha Pipeline",
        is_default=True,
    )
    db_session.add(pipe_a)
    await db_session.flush()

    stage_a = PipelineStage(
        organization_id=test_org.id,
        pipeline_id=pipe_a.id,
        name="Discovery",
        order=1,
        win_probability=20,
    )
    db_session.add(stage_a)
    await db_session.flush()

    deal_a = Deal(
        organization_id=test_org.id,
        pipeline_id=pipe_a.id,
        stage_id=stage_a.id,
        contact_id=contact_a.id,
        company_id=company_a.id,
        title="Alpha Strategic Contract",
        value=50000.0,
    )
    db_session.add(deal_a)
    await db_session.flush()

    # Org A Audit Logs:
    # log1: Day 1 - lead.created by owner
    log1 = AuditLog(
        organization_id=test_org.id,
        user_id=test_user_owner.id,
        action="lead.created",
        entity_type="lead",
        entity_id=lead_a.id,
        changes={"title": "Alpha Enterprise Lead", "status": "NEW"},
        ip_address="192.168.1.10",
        user_agent="Mozilla/5.0 TestBrowser",
        created_at=base_time + timedelta(days=1),
    )
    # log2: Day 2 - deal.stage_changed by member
    log2 = AuditLog(
        organization_id=test_org.id,
        user_id=test_user_member.id,
        action="deal.stage_changed",
        entity_type="deal",
        entity_id=deal_a.id,
        changes={"old_stage_id": "stage-0", "new_stage_id": stage_a.id},
        ip_address="192.168.1.20",
        created_at=base_time + timedelta(days=2),
    )
    # log3: Day 3 - deal.won by owner
    log3 = AuditLog(
        organization_id=test_org.id,
        user_id=test_user_owner.id,
        action="deal.won",
        entity_type="deal",
        entity_id=deal_a.id,
        changes={"deal_id": deal_a.id, "value": 50000.0, "status": "WON"},
        created_at=base_time + timedelta(days=3),
    )
    # log4: Day 4 - activity.created by owner
    log4 = AuditLog(
        organization_id=test_org.id,
        user_id=test_user_owner.id,
        action="activity.created",
        entity_type="activity",
        entity_id="act-uuid-4444",
        changes={"activity_type": "CALL", "duration_seconds": 300},
        created_at=base_time + timedelta(days=4),
    )
    db_session.add_all([log1, log2, log3, log4])

    # 2. Org B entities (different tenant)
    org_b = Organization(
        name="Org Beta",
        slug="org-beta",
        is_active=True,
    )
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

    log_b = AuditLog(
        organization_id=org_b.id,
        user_id=user_b.id,
        action="deal.won",
        entity_type="deal",
        entity_id="deal-b-9999",
        changes={"title": "Beta Confidential Deal", "value": 100000.0},
        created_at=base_time + timedelta(days=2),
    )
    db_session.add(log_b)

    await db_session.commit()
    await db_session.refresh(lead_a)
    await db_session.refresh(contact_a)
    await db_session.refresh(deal_a)
    await db_session.refresh(log1)
    await db_session.refresh(log2)
    await db_session.refresh(log3)
    await db_session.refresh(log4)
    await db_session.refresh(org_b)
    await db_session.refresh(user_b)
    await db_session.refresh(log_b)

    token_b = create_access_token(user_b.id, org_b.id, user_b.role)
    auth_headers_b = {"Authorization": f"Bearer {token_b}"}

    return {
        "base_time": base_time,
        "lead_a": lead_a,
        "contact_a": contact_a,
        "deal_a": deal_a,
        "stage_a": stage_a,
        "pipe_a": pipe_a,
        "log1": log1,
        "log2": log2,
        "log3": log3,
        "log4": log4,
        "org_b": org_b,
        "user_b": user_b,
        "log_b": log_b,
        "auth_headers_b": auth_headers_b,
    }


# ==============================================================================
# 1. Event-Driven Audit Capture on Real CRM Operations
# ==============================================================================


@pytest.mark.asyncio
async def test_event_driven_audit_capture(
    client: AsyncClient,
    auth_headers_owner: dict,
    test_user_owner: User,
    mock_celery_dispatch,
    seed_audit_test_data: dict,
):
    """Test that performing real CRM operations triggers automatic AuditLog creation."""
    data = seed_audit_test_data
    lead = data["lead_a"]
    deal = data["deal_a"]
    stage = data["stage_a"]

    # 1. Create a new lead -> triggers LEAD_CREATED -> audit record created
    lead_payload = {
        "title": "Live Audit Test Lead",
        "email": "audit_lead@live.com",
    }
    lead_res = await client.post("/api/v1/leads", json=lead_payload, headers=auth_headers_owner)
    assert lead_res.status_code == 201, lead_res.text
    new_lead_id = lead_res.json()["id"]

    # Verify audit log recorded for lead.created
    audit_res = await client.get(
        f"/api/v1/audit?entity_type=lead&entity_id={new_lead_id}",
        headers=auth_headers_owner,
    )
    assert audit_res.status_code == 200
    lead_audit_logs = audit_res.json()
    assert len(lead_audit_logs) >= 1
    assert lead_audit_logs[0]["action"] == "lead.created"
    assert lead_audit_logs[0]["entity_id"] == new_lead_id

    # 2. Log an activity -> triggers ACTIVITY_CREATED -> audit record created
    act_payload = {
        "activity_type": "CALL",
        "title": "Discovery Follow-up",
        "description": "Reviewed requirements with prospect",
        "lead_id": lead.id,
        "deal_id": deal.id,
        "duration_seconds": 180,
    }
    act_res = await client.post("/api/v1/activities", json=act_payload, headers=auth_headers_owner)
    assert act_res.status_code == 201, act_res.text
    act_id = act_res.json()["id"]

    audit_res = await client.get(
        f"/api/v1/audit?entity_type=activity&entity_id={act_id}",
        headers=auth_headers_owner,
    )
    assert audit_res.status_code == 200
    act_audit_logs = audit_res.json()
    assert len(act_audit_logs) == 1
    assert act_audit_logs[0]["action"] == "activity.created"
    assert act_audit_logs[0]["user_id"] == test_user_owner.id
    assert act_audit_logs[0]["changes"]["activity_type"] == "CALL"


# ==============================================================================
# 2. Listing and Single-Item Retrieval
# ==============================================================================


@pytest.mark.asyncio
async def test_audit_listing_and_retrieval(
    client: AsyncClient,
    auth_headers_owner: dict,
    test_user_owner: User,
    seed_audit_test_data: dict,
):
    """Test retrieving all logs and single-item retrieval with user hydration."""
    data = seed_audit_test_data
    log1 = data["log1"]

    # 1. Retrieve single audit log by ID
    res = await client.get(f"/api/v1/audit/{log1.id}", headers=auth_headers_owner)
    assert res.status_code == 200
    item = res.json()
    assert item["id"] == log1.id
    assert item["action"] == "lead.created"
    assert item["entity_type"] == "lead"
    assert item["entity_id"] == log1.entity_id
    assert item["user_id"] == test_user_owner.id
    assert item["user_name"] == f"{test_user_owner.first_name} {test_user_owner.last_name}"
    assert item["user_email"] == test_user_owner.email
    assert item["ip_address"] == "192.168.1.10"
    assert item["user_agent"] == "Mozilla/5.0 TestBrowser"

    # 2. Non-existent audit log -> 404
    res = await client.get("/api/v1/audit/nonexistent-uuid-1234", headers=auth_headers_owner)
    assert res.status_code == 404
    assert "Audit log not found." in res.text

    # 3. List all logs
    res = await client.get("/api/v1/audit", headers=auth_headers_owner)
    assert res.status_code == 200
    items = res.json()
    assert len(items) >= 4


# ==============================================================================
# 3. Filtering by User, Action, Entity, and Dates
# ==============================================================================


@pytest.mark.asyncio
async def test_audit_filtering_and_dates(
    client: AsyncClient,
    auth_headers_owner: dict,
    test_user_member: User,
    seed_audit_test_data: dict,
):
    """Test filtering by user_id, action, entity_type, entity_id, and date windows."""
    data = seed_audit_test_data
    base = data["base_time"]
    deal = data["deal_a"]
    log2 = data["log2"]
    log3 = data["log3"]

    # 1. Filter by user_id
    res = await client.get(f"/api/v1/audit?user_id={test_user_member.id}", headers=auth_headers_owner)
    assert res.status_code == 200
    items = res.json()
    assert len(items) == 1
    assert items[0]["id"] == log2.id

    # 2. Filter by action
    res = await client.get("/api/v1/audit?action=deal.won", headers=auth_headers_owner)
    assert res.status_code == 200
    items = res.json()
    assert len(items) == 1
    assert items[0]["id"] == log3.id

    # 3. Filter by entity_type
    res = await client.get("/api/v1/audit?entity_type=deal", headers=auth_headers_owner)
    assert res.status_code == 200
    items = res.json()
    assert len(items) == 2
    ids = {i["id"] for i in items}
    assert ids == {log2.id, log3.id}

    # 4. Filter by entity_id
    res = await client.get(f"/api/v1/audit?entity_id={deal.id}", headers=auth_headers_owner)
    assert res.status_code == 200
    items = res.json()
    assert len(items) == 2

    # 5. Date-window filter covering Day 2 and Day 3 (log2 and log3)
    start_dt = (base + timedelta(days=1, hours=12)).isoformat()
    end_dt = (base + timedelta(days=3, hours=12)).isoformat()
    res = await client.get(
        "/api/v1/audit",
        params={"start_date": start_dt, "end_date": end_dt},
        headers=auth_headers_owner,
    )
    assert res.status_code == 200
    items = res.json()
    assert len(items) == 2
    ids = {i["id"] for i in items}
    assert ids == {log2.id, log3.id}

    # 6. Inverted dates -> 400
    res = await client.get(
        "/api/v1/audit",
        params={"start_date": end_dt, "end_date": start_dt},
        headers=auth_headers_owner,
    )
    assert res.status_code == 400
    assert "Start date cannot be after end date." in res.text


# ==============================================================================
# 4. Search, Sorting, and Pagination
# ==============================================================================


@pytest.mark.asyncio
async def test_audit_search_sorting_pagination(
    client: AsyncClient,
    auth_headers_owner: dict,
    seed_audit_test_data: dict,
):
    """Test text search, dynamic sorting with allowlist, and pagination."""
    data = seed_audit_test_data
    log1 = data["log1"]  # Day 1, lead.created, entity_type: lead
    log2 = data["log2"]  # Day 2, deal.stage_changed, entity_type: deal
    log3 = data["log3"]  # Day 3, deal.won, entity_type: deal
    log4 = data["log4"]  # Day 4, activity.created, entity_type: activity

    # 1. Search action
    res = await client.get("/api/v1/audit?search=stage_changed", headers=auth_headers_owner)
    assert res.status_code == 200
    items = res.json()
    assert len(items) == 1
    assert items[0]["id"] == log2.id

    # 2. Search entity_type
    res = await client.get("/api/v1/audit?search=activity", headers=auth_headers_owner)
    assert res.status_code == 200
    items = res.json()
    assert len(items) == 1
    assert items[0]["id"] == log4.id

    # 3. Search no match
    res = await client.get("/api/v1/audit?search=nonexistent_token_xyz", headers=auth_headers_owner)
    assert res.status_code == 200
    assert len(res.json()) == 0

    # 4. Default sort: created_at desc (newest first: log4, log3, log2, log1)
    res = await client.get("/api/v1/audit", headers=auth_headers_owner)
    assert res.status_code == 200
    ids = [i["id"] for i in res.json()]
    assert ids == [log4.id, log3.id, log2.id, log1.id]

    # 5. Sort created_at asc (oldest first: log1, log2, log3, log4)
    res = await client.get("/api/v1/audit?sort_by=created_at&sort_order=asc", headers=auth_headers_owner)
    assert res.status_code == 200
    ids = [i["id"] for i in res.json()]
    assert ids == [log1.id, log2.id, log3.id, log4.id]

    # 6. Sort action asc
    # Alphabetical actions: "activity.created" (log4), "deal.stage_changed" (log2), "deal.won" (log3), "lead.created" (log1)
    res = await client.get("/api/v1/audit?sort_by=action&sort_order=asc", headers=auth_headers_owner)
    assert res.status_code == 200
    actions = [i["action"] for i in res.json()]
    assert actions == ["activity.created", "deal.stage_changed", "deal.won", "lead.created"]

    # 7. Invalid sort field -> 400
    res = await client.get("/api/v1/audit?sort_by=invalid_col", headers=auth_headers_owner)
    assert res.status_code == 400
    assert "Invalid sort field" in res.text

    # 8. Invalid sort order -> 400
    res = await client.get("/api/v1/audit?sort_order=reverse", headers=auth_headers_owner)
    assert res.status_code == 400
    assert "Invalid sort order" in res.text

    # 9. Pagination: limit=2 & offset=0, then limit=2 & offset=2
    res = await client.get("/api/v1/audit?limit=2&offset=0", headers=auth_headers_owner)
    assert res.status_code == 200
    assert len(res.json()) == 2
    assert res.json()[0]["id"] == log4.id

    res = await client.get("/api/v1/audit?limit=2&offset=2", headers=auth_headers_owner)
    assert res.status_code == 200
    assert len(res.json()) == 2
    assert res.json()[0]["id"] == log2.id


# ==============================================================================
# 5. Cross-Tenant Isolation
# ==============================================================================


@pytest.mark.asyncio
async def test_audit_cross_tenant_isolation(
    client: AsyncClient,
    auth_headers_owner: dict,
    seed_audit_test_data: dict,
):
    """Test that audit logs are strictly isolated by organization."""
    data = seed_audit_test_data
    log1 = data["log1"]
    log_b = data["log_b"]
    auth_headers_b = data["auth_headers_b"]

    # 1. Org A attempts to retrieve Org B audit log -> 404
    res = await client.get(f"/api/v1/audit/{log_b.id}", headers=auth_headers_owner)
    assert res.status_code == 404

    # 2. Org B attempts to retrieve Org A audit log -> 404
    res = await client.get(f"/api/v1/audit/{log1.id}", headers=auth_headers_b)
    assert res.status_code == 404

    # 3. Org A listing does NOT contain Org B logs
    res = await client.get("/api/v1/audit", headers=auth_headers_owner)
    assert res.status_code == 200
    ids_a = [i["id"] for i in res.json()]
    assert log1.id in ids_a
    assert log_b.id not in ids_a

    # 4. Org B listing contains only Org B logs
    res = await client.get("/api/v1/audit", headers=auth_headers_b)
    assert res.status_code == 200
    ids_b = [i["id"] for i in res.json()]
    assert log_b.id in ids_b
    assert log1.id not in ids_b


# ==============================================================================
# 6. RBAC Permissions Enforcement
# ==============================================================================


@pytest.mark.asyncio
async def test_audit_rbac_permissions(
    client: AsyncClient,
    auth_headers_owner: dict,
    auth_headers_manager: dict,
    auth_headers_member: dict,
    seed_audit_test_data: dict,
):
    """Test RBAC enforcement: 401 unauthenticated, 403 MEMBER, 200 MANAGER, 200 OWNER."""
    data = seed_audit_test_data
    log1 = data["log1"]

    # 1. Unauthenticated -> 401
    res = await client.get("/api/v1/audit")
    assert res.status_code == 401

    res = await client.get(f"/api/v1/audit/{log1.id}")
    assert res.status_code == 401

    # 2. Member role -> 403 Forbidden
    res = await client.get("/api/v1/audit", headers=auth_headers_member)
    assert res.status_code == 403

    res = await client.get(f"/api/v1/audit/{log1.id}", headers=auth_headers_member)
    assert res.status_code == 403

    # 3. Manager role -> 200 OK
    res = await client.get("/api/v1/audit", headers=auth_headers_manager)
    assert res.status_code == 200

    res = await client.get(f"/api/v1/audit/{log1.id}", headers=auth_headers_manager)
    assert res.status_code == 200
    assert res.json()["id"] == log1.id

    # 4. Owner role -> 200 OK
    res = await client.get("/api/v1/audit", headers=auth_headers_owner)
    assert res.status_code == 200

    res = await client.get(f"/api/v1/audit/{log1.id}", headers=auth_headers_owner)
    assert res.status_code == 200
    assert res.json()["id"] == log1.id
