import pytest
import pytest_asyncio
from datetime import datetime, timezone, timedelta
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.security import create_access_token, hash_password
from app.modules.activities.models import Activity, ActivityType
from app.modules.companies.models import Company
from app.modules.contacts.models import Contact
from app.modules.deals.models import Deal
from app.modules.leads.models import Lead
from app.modules.organizations.models import Organization
from app.modules.pipelines.models import Pipeline, PipelineStage
from app.modules.tasks.models import Task, TaskPriority, TaskType
from app.modules.users.models import User


@pytest_asyncio.fixture(scope="function")
async def seed_activities_test_data(
    db_session: AsyncSession,
    test_org: Organization,
    test_user_owner: User,
    test_user_member: User,
):
    """Seed comprehensive test entities across Org A and Org B."""
    # 1. Org A entities
    lead_a = Lead(
        organization_id=test_org.id,
        title="Alpha Lead Corp",
        assigned_to_id=test_user_owner.id,
        status="NEW",
    )
    db_session.add(lead_a)

    company_a = Company(
        organization_id=test_org.id,
        name="Alpha Industries",
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
        title="Alpha Enterprise Deal",
        value=50000.0,
    )
    db_session.add(deal_a)
    await db_session.flush()

    act_a = Activity(
        organization_id=test_org.id,
        user_id=test_user_owner.id,
        lead_id=lead_a.id,
        contact_id=contact_a.id,
        deal_id=deal_a.id,
        activity_type=ActivityType.CALL.value,
        title="Alpha Initial Call",
        description="Initial touchpoint with Alice",
        outcome="Connected",
        duration_seconds=300,
        performed_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    db_session.add(act_a)

    # 2. Org B entities (cross-tenant)
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

    lead_b = Lead(
        organization_id=org_b.id,
        title="Beta Lead Corp",
        assigned_to_id=user_b.id,
        status="NEW",
    )
    db_session.add(lead_b)

    company_b = Company(
        organization_id=org_b.id,
        name="Beta Confidential Corp",
    )
    db_session.add(company_b)
    await db_session.flush()

    contact_b = Contact(
        organization_id=org_b.id,
        company_id=company_b.id,
        first_name="Bob",
        last_name="Beta",
        email="bob@beta.com",
    )
    db_session.add(contact_b)

    pipe_b = Pipeline(
        organization_id=org_b.id,
        name="Beta Pipeline",
        is_default=True,
    )
    db_session.add(pipe_b)
    await db_session.flush()

    stage_b = PipelineStage(
        organization_id=org_b.id,
        pipeline_id=pipe_b.id,
        name="Beta Stage",
        order=1,
        win_probability=50,
    )
    db_session.add(stage_b)
    await db_session.flush()

    deal_b = Deal(
        organization_id=org_b.id,
        pipeline_id=pipe_b.id,
        stage_id=stage_b.id,
        contact_id=contact_b.id,
        company_id=company_b.id,
        title="Beta Deal",
        value=100000.0,
    )
    db_session.add(deal_b)
    await db_session.flush()

    act_b = Activity(
        organization_id=org_b.id,
        user_id=user_b.id,
        lead_id=lead_b.id,
        contact_id=contact_b.id,
        deal_id=deal_b.id,
        activity_type=ActivityType.CALL.value,
        title="Beta Secret Call",
        description="Confidential interaction in Org B",
        outcome="Interested",
        duration_seconds=600,
        performed_at=datetime.now(timezone.utc),
    )
    db_session.add(act_b)

    await db_session.commit()
    await db_session.refresh(lead_a)
    await db_session.refresh(contact_a)
    await db_session.refresh(deal_a)
    await db_session.refresh(act_a)
    await db_session.refresh(org_b)
    await db_session.refresh(user_b)
    await db_session.refresh(lead_b)
    await db_session.refresh(contact_b)
    await db_session.refresh(deal_b)
    await db_session.refresh(act_b)

    token_b = create_access_token(user_b.id, org_b.id, user_b.role)
    auth_headers_b = {"Authorization": f"Bearer {token_b}"}

    return {
        "lead_a": lead_a,
        "contact_a": contact_a,
        "deal_a": deal_a,
        "act_a": act_a,
        "org_b": org_b,
        "user_b": user_b,
        "lead_b": lead_b,
        "contact_b": contact_b,
        "deal_b": deal_b,
        "act_b": act_b,
        "auth_headers_b": auth_headers_b,
    }


# ==============================================================================
# 1. Cross-Tenant Relationship Validation on Create
# ==============================================================================


@pytest.mark.asyncio
async def test_create_activity_cross_tenant_rejection(
    client: AsyncClient,
    auth_headers_owner: dict,
    seed_activities_test_data: dict,
):
    """Attempting to log an activity with foreign entities returns 404."""
    data = seed_activities_test_data
    base_payload = {
        "title": "Validation Activity",
        "activity_type": "CALL",
        "description": "Cross tenant test",
        "performed_at": datetime.now(timezone.utc).isoformat(),
    }

    # Foreign lead_id (from Org B)
    res = await client.post(
        "/api/v1/activities",
        json={**base_payload, "lead_id": data["lead_b"].id},
        headers=auth_headers_owner,
    )
    assert res.status_code == 404
    assert res.json()["error"]["message"] == "Lead not found."

    # Foreign contact_id (from Org B)
    res = await client.post(
        "/api/v1/activities",
        json={**base_payload, "contact_id": data["contact_b"].id},
        headers=auth_headers_owner,
    )
    assert res.status_code == 404
    assert res.json()["error"]["message"] == "Contact not found."

    # Foreign deal_id (from Org B)
    res = await client.post(
        "/api/v1/activities",
        json={**base_payload, "deal_id": data["deal_b"].id},
        headers=auth_headers_owner,
    )
    assert res.status_code == 404
    assert res.json()["error"]["message"] == "Deal not found."

    # Valid creation with Org A entities
    res = await client.post(
        "/api/v1/activities",
        json={
            **base_payload,
            "lead_id": data["lead_a"].id,
            "contact_id": data["contact_a"].id,
            "deal_id": data["deal_a"].id,
        },
        headers=auth_headers_owner,
    )
    assert res.status_code == 201
    created = res.json()
    assert created["lead_id"] == data["lead_a"].id
    assert created["contact_id"] == data["contact_a"].id
    assert created["deal_id"] == data["deal_a"].id
    assert created["lead_title"] == "Alpha Lead Corp"
    assert created["contact_name"] == "Alice Alpha"
    assert created["deal_title"] == "Alpha Enterprise Deal"

    # Valid creation without any parent entity (standalone meeting note)
    res_standalone = await client.post(
        "/api/v1/activities",
        json={**base_payload, "title": "Standalone Team Sync"},
        headers=auth_headers_owner,
    )
    assert res_standalone.status_code == 201
    assert res_standalone.json()["title"] == "Standalone Team Sync"


# ==============================================================================
# 2. Cross-Tenant Relationship Validation on PATCH
# ==============================================================================


@pytest.mark.asyncio
async def test_update_activity_cross_tenant_rejection(
    client: AsyncClient,
    auth_headers_owner: dict,
    seed_activities_test_data: dict,
):
    """Attempting to update an existing activity with foreign entities returns 404."""
    data = seed_activities_test_data
    # Create valid activity first
    create_res = await client.post(
        "/api/v1/activities",
        json={
            "title": "Activity To Update",
            "activity_type": "NOTE",
            "performed_at": datetime.now(timezone.utc).isoformat(),
        },
        headers=auth_headers_owner,
    )
    assert create_res.status_code == 201
    activity_id = create_res.json()["id"]

    # Update with foreign lead_id
    res = await client.patch(
        f"/api/v1/activities/{activity_id}",
        json={"lead_id": data["lead_b"].id},
        headers=auth_headers_owner,
    )
    assert res.status_code == 404
    assert res.json()["error"]["message"] == "Lead not found."

    # Update with foreign contact_id
    res = await client.patch(
        f"/api/v1/activities/{activity_id}",
        json={"contact_id": data["contact_b"].id},
        headers=auth_headers_owner,
    )
    assert res.status_code == 404
    assert res.json()["error"]["message"] == "Contact not found."

    # Update with foreign deal_id
    res = await client.patch(
        f"/api/v1/activities/{activity_id}",
        json={"deal_id": data["deal_b"].id},
        headers=auth_headers_owner,
    )
    assert res.status_code == 404
    assert res.json()["error"]["message"] == "Deal not found."

    # Valid update with Org A entities
    res = await client.patch(
        f"/api/v1/activities/{activity_id}",
        json={
            "lead_id": data["lead_a"].id,
            "contact_id": data["contact_a"].id,
            "deal_id": data["deal_a"].id,
        },
        headers=auth_headers_owner,
    )
    assert res.status_code == 200
    updated = res.json()
    assert updated["lead_id"] == data["lead_a"].id
    assert updated["contact_id"] == data["contact_a"].id
    assert updated["deal_id"] == data["deal_a"].id


# ==============================================================================
# 3. Single Activity Retrieval & Cross-Tenant Isolation
# ==============================================================================


@pytest.mark.asyncio
async def test_get_single_activity_and_tenant_isolation(
    client: AsyncClient,
    auth_headers_owner: dict,
    seed_activities_test_data: dict,
):
    """GET /api/v1/activities/{activity_id} returns activity details and enforces tenant isolation."""
    data = seed_activities_test_data
    act_a = data["act_a"]
    act_b = data["act_b"]

    # 1. Org A retrieves its own activity
    res = await client.get(f"/api/v1/activities/{act_a.id}", headers=auth_headers_owner)
    assert res.status_code == 200
    act_data = res.json()
    assert act_data["id"] == act_a.id
    assert act_data["title"] == "Alpha Initial Call"
    assert act_data["outcome"] == "Connected"
    assert act_data["user_name"] == "Alice Owner"
    assert act_data["lead_title"] == "Alpha Lead Corp"
    assert act_data["contact_name"] == "Alice Alpha"
    assert act_data["deal_title"] == "Alpha Enterprise Deal"

    # 2. Non-existent activity ID -> 404
    not_found = await client.get("/api/v1/activities/non-existent-uuid-1234", headers=auth_headers_owner)
    assert not_found.status_code == 404
    assert not_found.json()["error"]["message"] == "Activity not found."

    # 3. Org A cannot access Org B's activity -> 404
    cross_tenant = await client.get(f"/api/v1/activities/{act_b.id}", headers=auth_headers_owner)
    assert cross_tenant.status_code == 404
    assert cross_tenant.json()["error"]["message"] == "Activity not found."

    # 4. Org B can access its own activity
    beta_res = await client.get(f"/api/v1/activities/{act_b.id}", headers=data["auth_headers_b"])
    assert beta_res.status_code == 200
    assert beta_res.json()["title"] == "Beta Secret Call"


# ==============================================================================
# 4. Activity Update & Delete Lifecycle
# ==============================================================================


@pytest.mark.asyncio
async def test_update_and_delete_activity_lifecycle(
    client: AsyncClient,
    auth_headers_owner: dict,
    auth_headers_member: dict,
    seed_activities_test_data: dict,
):
    """Test full update and delete lifecycle including RBAC and cross-tenant protection."""
    data = seed_activities_test_data
    # 1. Create activity
    create_res = await client.post(
        "/api/v1/activities",
        json={
            "title": "Interactive Client Session",
            "activity_type": "MEETING",
            "description": "Initial workshop",
            "outcome": "Rescheduled",
            "duration_seconds": 1800,
            "performed_at": datetime.now(timezone.utc).isoformat(),
        },
        headers=auth_headers_owner,
    )
    assert create_res.status_code == 201
    act_id = create_res.json()["id"]

    # 2. PATCH update attributes
    patch_res = await client.patch(
        f"/api/v1/activities/{act_id}",
        json={
            "title": "Completed Client Workshop",
            "outcome": "Interested",
            "duration_seconds": 3600,
            "description": "Workshop concluded with agreement on architecture.",
        },
        headers=auth_headers_owner,
    )
    assert patch_res.status_code == 200
    updated = patch_res.json()
    assert updated["title"] == "Completed Client Workshop"
    assert updated["outcome"] == "Interested"
    assert updated["duration_seconds"] == 3600
    assert "agreement on architecture" in updated["description"]

    # 3. Cross-tenant update rejection (Org A tries to update Org B's activity)
    cross_patch = await client.patch(
        f"/api/v1/activities/{data['act_b'].id}",
        json={"title": "Hacked Title"},
        headers=auth_headers_owner,
    )
    assert cross_patch.status_code == 404
    assert cross_patch.json()["error"]["message"] == "Activity not found."

    # 4. Cross-tenant delete rejection (Org A tries to delete Org B's activity)
    cross_delete = await client.delete(
        f"/api/v1/activities/{data['act_b'].id}",
        headers=auth_headers_owner,
    )
    assert cross_delete.status_code == 404
    assert cross_delete.json()["error"]["message"] == "Activity not found."

    # 5. Member role cannot delete activities (RBAC 403)
    member_delete = await client.delete(
        f"/api/v1/activities/{act_id}",
        headers=auth_headers_member,
    )
    assert member_delete.status_code == 403

    # 6. Owner deletes activity
    owner_delete = await client.delete(
        f"/api/v1/activities/{act_id}",
        headers=auth_headers_owner,
    )
    assert owner_delete.status_code == 204

    # 7. Verification: GET returns 404 after deletion
    get_after_del = await client.get(f"/api/v1/activities/{act_id}", headers=auth_headers_owner)
    assert get_after_del.status_code == 404


# ==============================================================================
# 5. Timeline Filtering, Date Range & Pagination
# ==============================================================================


@pytest.mark.asyncio
async def test_timeline_filtering_and_pagination(
    client: AsyncClient,
    auth_headers_owner: dict,
    test_user_owner: User,
    test_user_member: User,
):
    """Test filtering by user_id, activity_type, performed_at range, and pagination."""
    base_time = datetime(2026, 6, 1, 10, 0, 0, tzinfo=timezone.utc)

    # Activity 1: Owner, CALL, Day 1
    a1 = await client.post(
        "/api/v1/activities",
        json={
            "title": "Day 1 Discovery Call",
            "activity_type": "CALL",
            "performed_at": (base_time + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
        headers=auth_headers_owner,
    )
    # Activity 2: Member, MEETING, Day 3
    token_member = create_access_token(test_user_member.id, test_user_member.organization_id, test_user_member.role)
    a2 = await client.post(
        "/api/v1/activities",
        json={
            "title": "Day 3 Technical Review",
            "activity_type": "MEETING",
            "performed_at": (base_time + timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
        headers={"Authorization": f"Bearer {token_member}"},
    )
    # Activity 3: Owner, NOTE, Day 5
    a3 = await client.post(
        "/api/v1/activities",
        json={
            "title": "Day 5 Pricing Note",
            "activity_type": "NOTE",
            "performed_at": (base_time + timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
        headers=auth_headers_owner,
    )
    assert a1.status_code == 201
    assert a2.status_code == 201
    assert a3.status_code == 201

    # 1. Filter by user_id (member only)
    user_res = await client.get(f"/api/v1/activities?user_id={test_user_member.id}", headers=auth_headers_owner)
    assert user_res.status_code == 200
    user_acts = user_res.json()
    assert len(user_acts) == 1
    assert user_acts[0]["title"] == "Day 3 Technical Review"

    # 2. Filter by activity_type (CALL only)
    type_res = await client.get("/api/v1/activities?activity_type=CALL", headers=auth_headers_owner)
    assert type_res.status_code == 200
    assert all(a["activity_type"] == "CALL" for a in type_res.json())

    # 3. Date range filter (Day 1 to Day 4)
    s_dt = (base_time + timedelta(days=0)).strftime("%Y-%m-%dT%H:%M:%SZ")
    e_dt = (base_time + timedelta(days=4)).strftime("%Y-%m-%dT%H:%M:%SZ")
    range_res = await client.get(f"/api/v1/activities?start_date={s_dt}&end_date={e_dt}", headers=auth_headers_owner)
    assert range_res.status_code == 200
    range_titles = [a["title"] for a in range_res.json()]
    assert "Day 1 Discovery Call" in range_titles
    assert "Day 3 Technical Review" in range_titles
    assert "Day 5 Pricing Note" not in range_titles

    # 4. Inverted date range -> 400
    bad_range = await client.get(f"/api/v1/activities?start_date={e_dt}&end_date={s_dt}", headers=auth_headers_owner)
    assert bad_range.status_code == 400
    assert bad_range.json()["error"]["message"] == "Start date cannot be after end date."

    # 5. Pagination
    p1 = await client.get(
        "/api/v1/activities?limit=2&offset=0&sort_by=performed_at&sort_order=asc",
        headers=auth_headers_owner,
    )
    assert p1.status_code == 200
    assert len(p1.json()) == 2
    assert p1.json()[0]["title"] == "Day 1 Discovery Call"
    assert p1.json()[1]["title"] == "Day 3 Technical Review"

    p2 = await client.get(
        "/api/v1/activities?limit=2&offset=2&sort_by=performed_at&sort_order=asc",
        headers=auth_headers_owner,
    )
    assert p2.status_code == 200
    assert len(p2.json()) >= 1
    assert p2.json()[0]["title"] == "Day 5 Pricing Note"


# ==============================================================================
# 6. Timeline Search & Sorting
# ==============================================================================


@pytest.mark.asyncio
async def test_timeline_search_and_sorting(
    client: AsyncClient,
    auth_headers_owner: dict,
):
    """Test text search across title, description, and outcome, and allowlisted sorting."""
    base_time = datetime(2026, 7, 1, 10, 0, 0, tzinfo=timezone.utc)

    # 1. Seed activities with specific search keywords
    await client.post(
        "/api/v1/activities",
        json={
            "title": "Alpha Customer Onboarding",
            "description": "Configuring SSO and active directory sync",
            "outcome": "Connected",
            "activity_type": "MEETING",
            "performed_at": (base_time + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
        headers=auth_headers_owner,
    )
    await client.post(
        "/api/v1/activities",
        json={
            "title": "Beta Proposal Followup",
            "description": "Reviewed enterprise SLA terms",
            "outcome": "Left Voicemail",
            "activity_type": "CALL",
            "performed_at": (base_time + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
        headers=auth_headers_owner,
    )
    await client.post(
        "/api/v1/activities",
        json={
            "title": "Executive Strategy Sync",
            "description": "Discussion on Q3 expansion",
            "outcome": "Interested",
            "activity_type": "NOTE",
            "performed_at": (base_time + timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
        headers=auth_headers_owner,
    )

    # Search in title (case-insensitive)
    res_title = await client.get("/api/v1/activities?search=onboarding", headers=auth_headers_owner)
    assert res_title.status_code == 200
    assert len(res_title.json()) == 1
    assert res_title.json()[0]["title"] == "Alpha Customer Onboarding"

    # Search in description
    res_desc = await client.get("/api/v1/activities?search=SLA", headers=auth_headers_owner)
    assert res_desc.status_code == 200
    assert len(res_desc.json()) == 1
    assert res_desc.json()[0]["title"] == "Beta Proposal Followup"

    # Search in outcome
    res_outcome = await client.get("/api/v1/activities?search=voicemail", headers=auth_headers_owner)
    assert res_outcome.status_code == 200
    assert len(res_outcome.json()) == 1
    assert res_outcome.json()[0]["title"] == "Beta Proposal Followup"

    # Search with no match
    res_none = await client.get("/api/v1/activities?search=NonExistentQueryXYZ", headers=auth_headers_owner)
    assert res_none.status_code == 200
    assert len(res_none.json()) == 0

    # Sorting by performed_at asc
    sort_time_asc = await client.get("/api/v1/activities?sort_by=performed_at&sort_order=asc", headers=auth_headers_owner)
    assert sort_time_asc.status_code == 200
    titles_time_asc = [a["title"] for a in sort_time_asc.json()]
    assert titles_time_asc == [
        "Alpha Customer Onboarding",
        "Beta Proposal Followup",
        "Executive Strategy Sync",
    ]

    # Sorting by title asc
    sort_title_asc = await client.get("/api/v1/activities?sort_by=title&sort_order=asc", headers=auth_headers_owner)
    assert sort_title_asc.status_code == 200
    titles_asc = [a["title"] for a in sort_title_asc.json()]
    assert titles_asc == [
        "Alpha Customer Onboarding",
        "Beta Proposal Followup",
        "Executive Strategy Sync",
    ]

    # Invalid sort_by field -> 400
    bad_sort = await client.get("/api/v1/activities?sort_by=password", headers=auth_headers_owner)
    assert bad_sort.status_code == 400
    assert "Invalid sort field" in bad_sort.json()["error"]["message"]

    # Invalid sort_order -> 400
    bad_order = await client.get("/api/v1/activities?sort_order=sideways", headers=auth_headers_owner)
    assert bad_order.status_code == 400
    assert "Invalid sort order" in bad_order.json()["error"]["message"]


# ==============================================================================
# 7. Workflow Event Integration: Proposal Follow-Up Regression
# ==============================================================================


@pytest.mark.asyncio
async def test_proposal_activity_workflow_integration(
    client: AsyncClient,
    auth_headers_owner: dict,
    seed_activities_test_data: dict,
    db_session: AsyncSession,
):
    """Logging a PROPOSAL activity automatically triggers the proposal follow-up task workflow."""
    data = seed_activities_test_data
    deal = data["deal_a"]

    # 1. Log a PROPOSAL activity against deal_a
    act_res = await client.post(
        "/api/v1/activities",
        json={
            "deal_id": deal.id,
            "activity_type": "PROPOSAL",
            "title": "Sent Global Enterprise Proposal",
            "description": "500-seat annual contract with SLA addendum.",
            "performed_at": datetime.now(timezone.utc).isoformat(),
        },
        headers=auth_headers_owner,
    )
    assert act_res.status_code == 201

    # 2. Check that follow-up task was generated by handle_proposal_sent
    tasks_res = await client.get(f"/api/v1/tasks?deal_id={deal.id}", headers=auth_headers_owner)
    assert tasks_res.status_code == 200
    tasks = tasks_res.json()
    followup_task = next((t for t in tasks if "Follow up on proposal" in t["title"]), None)
    assert followup_task is not None
    assert followup_task["priority"] == TaskPriority.MEDIUM.value
    assert followup_task["task_type"] == TaskType.FOLLOW_UP.value
