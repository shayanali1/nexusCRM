import pytest
import pytest_asyncio
from datetime import datetime, timezone, timedelta
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.security import create_access_token, hash_password
from app.modules.companies.models import Company
from app.modules.contacts.models import Contact
from app.modules.deals.models import Deal
from app.modules.leads.models import Lead
from app.modules.organizations.models import Organization
from app.modules.pipelines.models import Pipeline, PipelineStage
from app.modules.tasks.models import Task, TaskPriority, TaskStatus, TaskType
from app.modules.users.models import User


@pytest_asyncio.fixture(scope="function")
async def seed_tasks_test_data(
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

    # Inactive user in Org A
    inactive_user_a = User(
        organization_id=test_org.id,
        email="inactive@alpha.com",
        hashed_password=hash_password("password123"),
        first_name="Inactive",
        last_name="User",
        role="MEMBER",
        is_active=False,
    )
    db_session.add(inactive_user_a)

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

    task_b = Task(
        organization_id=org_b.id,
        title="Beta Task 1",
        task_type=TaskType.FOLLOW_UP.value,
        priority=TaskPriority.HIGH.value,
        status=TaskStatus.PENDING.value,
        due_date=datetime.now(timezone.utc) + timedelta(days=2),
        assigned_to_id=user_b.id,
    )
    db_session.add(task_b)

    await db_session.commit()
    await db_session.refresh(lead_a)
    await db_session.refresh(contact_a)
    await db_session.refresh(deal_a)
    await db_session.refresh(inactive_user_a)
    await db_session.refresh(org_b)
    await db_session.refresh(user_b)
    await db_session.refresh(lead_b)
    await db_session.refresh(contact_b)
    await db_session.refresh(deal_b)
    await db_session.refresh(task_b)

    token_b = create_access_token(user_b.id, org_b.id, user_b.role)
    auth_headers_b = {"Authorization": f"Bearer {token_b}"}

    return {
        "lead_a": lead_a,
        "contact_a": contact_a,
        "deal_a": deal_a,
        "inactive_user_a": inactive_user_a,
        "org_b": org_b,
        "user_b": user_b,
        "lead_b": lead_b,
        "contact_b": contact_b,
        "deal_b": deal_b,
        "task_b": task_b,
        "auth_headers_b": auth_headers_b,
    }


# ==============================================================================
# 1. Cross-Tenant Relationship Validation
# ==============================================================================


@pytest.mark.asyncio
async def test_create_task_cross_tenant_rejection(
    client: AsyncClient,
    auth_headers_owner: dict,
    seed_tasks_test_data: dict,
):
    """Attempting to create a task with foreign or invalid entities returns 404."""
    data = seed_tasks_test_data
    base_payload = {
        "title": "Validation Test Task",
        "due_date": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        "task_type": "FOLLOW_UP",
        "priority": "MEDIUM",
    }

    # Foreign lead_id (from Org B)
    res = await client.post(
        "/api/v1/tasks",
        json={**base_payload, "lead_id": data["lead_b"].id},
        headers=auth_headers_owner,
    )
    assert res.status_code == 404
    assert res.json()["error"]["message"] == "Lead not found."

    # Foreign contact_id (from Org B)
    res = await client.post(
        "/api/v1/tasks",
        json={**base_payload, "contact_id": data["contact_b"].id},
        headers=auth_headers_owner,
    )
    assert res.status_code == 404
    assert res.json()["error"]["message"] == "Contact not found."

    # Foreign deal_id (from Org B)
    res = await client.post(
        "/api/v1/tasks",
        json={**base_payload, "deal_id": data["deal_b"].id},
        headers=auth_headers_owner,
    )
    assert res.status_code == 404
    assert res.json()["error"]["message"] == "Deal not found."

    # Foreign assigned_to_id (from Org B)
    res = await client.post(
        "/api/v1/tasks",
        json={**base_payload, "assigned_to_id": data["user_b"].id},
        headers=auth_headers_owner,
    )
    assert res.status_code == 404
    assert res.json()["error"]["message"] == "User not found."

    # Inactive user in Org A
    res = await client.post(
        "/api/v1/tasks",
        json={**base_payload, "assigned_to_id": data["inactive_user_a"].id},
        headers=auth_headers_owner,
    )
    assert res.status_code == 404
    assert res.json()["error"]["message"] == "User not found."

    # Successful creation with valid Org A entities
    res = await client.post(
        "/api/v1/tasks",
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


@pytest.mark.asyncio
async def test_update_task_cross_tenant_rejection(
    client: AsyncClient,
    auth_headers_owner: dict,
    seed_tasks_test_data: dict,
):
    """Attempting to update an existing task with foreign or invalid entities returns 404."""
    data = seed_tasks_test_data
    # Create valid task first
    create_res = await client.post(
        "/api/v1/tasks",
        json={
            "title": "Task To Update",
            "due_date": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        },
        headers=auth_headers_owner,
    )
    assert create_res.status_code == 201
    task_id = create_res.json()["id"]

    # Update with foreign lead_id
    res = await client.patch(
        f"/api/v1/tasks/{task_id}",
        json={"lead_id": data["lead_b"].id},
        headers=auth_headers_owner,
    )
    assert res.status_code == 404
    assert res.json()["error"]["message"] == "Lead not found."

    # Update with foreign contact_id
    res = await client.patch(
        f"/api/v1/tasks/{task_id}",
        json={"contact_id": data["contact_b"].id},
        headers=auth_headers_owner,
    )
    assert res.status_code == 404
    assert res.json()["error"]["message"] == "Contact not found."

    # Update with foreign deal_id
    res = await client.patch(
        f"/api/v1/tasks/{task_id}",
        json={"deal_id": data["deal_b"].id},
        headers=auth_headers_owner,
    )
    assert res.status_code == 404
    assert res.json()["error"]["message"] == "Deal not found."

    # Update with foreign assigned_to_id
    res = await client.patch(
        f"/api/v1/tasks/{task_id}",
        json={"assigned_to_id": data["user_b"].id},
        headers=auth_headers_owner,
    )
    assert res.status_code == 404
    assert res.json()["error"]["message"] == "User not found."

    # Update with inactive user
    res = await client.patch(
        f"/api/v1/tasks/{task_id}",
        json={"assigned_to_id": data["inactive_user_a"].id},
        headers=auth_headers_owner,
    )
    assert res.status_code == 404
    assert res.json()["error"]["message"] == "User not found."

    # Valid update with Org A entities
    res = await client.patch(
        f"/api/v1/tasks/{task_id}",
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
# 2. Single Task Retrieval (GET /api/v1/tasks/{task_id})
# ==============================================================================


@pytest.mark.asyncio
async def test_get_single_task(
    client: AsyncClient,
    auth_headers_owner: dict,
    seed_tasks_test_data: dict,
):
    """GET /api/v1/tasks/{task_id} retrieves single task with relationship details and checks tenant isolation."""
    data = seed_tasks_test_data
    # 1. Create a task in Org A with relations
    res = await client.post(
        "/api/v1/tasks",
        json={
            "title": "Alpha Detailed Task",
            "description": "Comprehensive follow-up description",
            "due_date": (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(),  # Past due
            "priority": "HIGH",
            "task_type": "FOLLOW_UP",
            "lead_id": data["lead_a"].id,
            "contact_id": data["contact_a"].id,
            "deal_id": data["deal_a"].id,
        },
        headers=auth_headers_owner,
    )
    assert res.status_code == 201
    task_id = res.json()["id"]

    # 2. Retrieve via GET /api/v1/tasks/{task_id}
    get_res = await client.get(f"/api/v1/tasks/{task_id}", headers=auth_headers_owner)
    assert get_res.status_code == 200
    task_data = get_res.json()
    assert task_data["id"] == task_id
    assert task_data["title"] == "Alpha Detailed Task"
    assert task_data["description"] == "Comprehensive follow-up description"
    assert task_data["priority"] == "HIGH"
    assert task_data["lead_title"] == "Alpha Lead Corp"
    assert task_data["contact_name"] == "Alice Alpha"
    assert task_data["deal_title"] == "Alpha Enterprise Deal"
    assert task_data["is_overdue"] is True

    # 3. Retrieve non-existent task
    not_found_res = await client.get("/api/v1/tasks/non-existent-uuid-1234", headers=auth_headers_owner)
    assert not_found_res.status_code == 404
    assert not_found_res.json()["error"]["message"] == "Task not found."

    # 4. Cross-tenant isolation: Org A cannot retrieve Org B's task
    cross_res = await client.get(f"/api/v1/tasks/{data['task_b'].id}", headers=auth_headers_owner)
    assert cross_res.status_code == 404
    assert cross_res.json()["error"]["message"] == "Task not found."

    # 5. Org B can retrieve its own task
    beta_res = await client.get(f"/api/v1/tasks/{data['task_b'].id}", headers=data["auth_headers_b"])
    assert beta_res.status_code == 200
    assert beta_res.json()["title"] == "Beta Task 1"


# ==============================================================================
# 3. List Filtering, Search & Sorting
# ==============================================================================


@pytest.mark.asyncio
async def test_tasks_search_and_sorting(
    client: AsyncClient,
    auth_headers_owner: dict,
    test_user_owner: User,
    test_user_member: User,
):
    """Test search, allowlisted sort fields, sort directions, and invalid parameters."""
    base_time = datetime(2026, 4, 1, 10, 0, 0, tzinfo=timezone.utc)

    # Create 3 tasks with distinct attributes
    t1_res = await client.post(
        "/api/v1/tasks",
        json={
            "title": "Alpha Contract Review",
            "description": "Review enterprise service agreement terms",
            "due_date": (base_time + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "priority": "LOW",
            "task_type": "OTHER",
            "assigned_to_id": test_user_owner.id,
        },
        headers=auth_headers_owner,
    )
    t2_res = await client.post(
        "/api/v1/tasks",
        json={
            "title": "Beta Demo Followup",
            "description": "Send meeting notes and pricing proposal",
            "due_date": (base_time + timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "priority": "HIGH",
            "task_type": "FOLLOW_UP",
            "assigned_to_id": test_user_member.id,
        },
        headers=auth_headers_owner,
    )
    t3_res = await client.post(
        "/api/v1/tasks",
        json={
            "title": "Gamma Client Checkin",
            "description": "Quarterly business review contract",
            "due_date": (base_time + timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "priority": "MEDIUM",
            "task_type": "CALL",
            "assigned_to_id": test_user_owner.id,
        },
        headers=auth_headers_owner,
    )
    assert t1_res.status_code == 201
    assert t2_res.status_code == 201
    assert t3_res.status_code == 201

    # 1. Search across title
    search_res = await client.get("/api/v1/tasks?search=demo", headers=auth_headers_owner)
    assert search_res.status_code == 200
    search_data = search_res.json()
    assert len(search_data) == 1
    assert search_data[0]["title"] == "Beta Demo Followup"

    # 2. Search across description (case-insensitive)
    search_res2 = await client.get("/api/v1/tasks?search=PRICING", headers=auth_headers_owner)
    assert search_res2.status_code == 200
    assert len(search_res2.json()) == 1
    assert search_res2.json()[0]["title"] == "Beta Demo Followup"

    # Search with multiple matches ("contract" in t1 title and t3 description)
    search_res3 = await client.get("/api/v1/tasks?search=contract", headers=auth_headers_owner)
    assert search_res3.status_code == 200
    assert len(search_res3.json()) == 2

    # Search with no match
    search_res4 = await client.get("/api/v1/tasks?search=NonExistentTermXYZ", headers=auth_headers_owner)
    assert search_res4.status_code == 200
    assert len(search_res4.json()) == 0

    # 3. Sort by due_date asc (default)
    sort_due_asc = await client.get("/api/v1/tasks?sort_by=due_date&sort_order=asc", headers=auth_headers_owner)
    assert sort_due_asc.status_code == 200
    due_asc_titles = [t["title"] for t in sort_due_asc.json()]
    assert due_asc_titles == ["Alpha Contract Review", "Gamma Client Checkin", "Beta Demo Followup"]

    # Sort by due_date desc
    sort_due_desc = await client.get("/api/v1/tasks?sort_by=due_date&sort_order=desc", headers=auth_headers_owner)
    assert sort_due_desc.status_code == 200
    due_desc_titles = [t["title"] for t in sort_due_desc.json()]
    assert due_desc_titles == ["Beta Demo Followup", "Gamma Client Checkin", "Alpha Contract Review"]

    # Sort by title asc
    sort_title_asc = await client.get("/api/v1/tasks?sort_by=title&sort_order=asc", headers=auth_headers_owner)
    assert sort_title_asc.status_code == 200
    title_asc_titles = [t["title"] for t in sort_title_asc.json()]
    assert title_asc_titles == ["Alpha Contract Review", "Beta Demo Followup", "Gamma Client Checkin"]

    # Sort by priority desc
    sort_priority_desc = await client.get("/api/v1/tasks?sort_by=priority&sort_order=desc", headers=auth_headers_owner)
    assert sort_priority_desc.status_code == 200

    # 4. Invalid sort_by field -> 400
    bad_sort = await client.get("/api/v1/tasks?sort_by=password", headers=auth_headers_owner)
    assert bad_sort.status_code == 400
    assert "Invalid sort field" in bad_sort.json()["error"]["message"]

    # 5. Invalid sort_order -> 400
    bad_order = await client.get("/api/v1/tasks?sort_order=sideways", headers=auth_headers_owner)
    assert bad_order.status_code == 400
    assert "Invalid sort order" in bad_order.json()["error"]["message"]


@pytest.mark.asyncio
async def test_tasks_date_range_filtering_and_pagination(
    client: AsyncClient,
    auth_headers_owner: dict,
):
    """Test start_date and end_date filtering on Task.due_date and pagination limits."""
    # Create 3 tasks with distinct dates: Day 1, Day 3, Day 5
    d1 = datetime(2026, 5, 10, 12, 0, 0, tzinfo=timezone.utc)
    d2 = datetime(2026, 5, 12, 12, 0, 0, tzinfo=timezone.utc)
    d3 = datetime(2026, 5, 15, 12, 0, 0, tzinfo=timezone.utc)

    for i, dt in enumerate([d1, d2, d3], start=1):
        res = await client.post(
            "/api/v1/tasks",
            json={
                "title": f"Range Task {i}",
                "due_date": dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
            headers=auth_headers_owner,
        )
        assert res.status_code == 201

    # Filter strictly covering Day 1 to Day 3
    s_filter = datetime(2026, 5, 9, 0, 0, 0, tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    e_filter = datetime(2026, 5, 13, 0, 0, 0, tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    range_res = await client.get(
        f"/api/v1/tasks?start_date={s_filter}&end_date={e_filter}",
        headers=auth_headers_owner,
    )
    assert range_res.status_code == 200
    range_titles = [t["title"] for t in range_res.json()]
    assert "Range Task 1" in range_titles
    assert "Range Task 2" in range_titles
    assert "Range Task 3" not in range_titles

    # Start date after end date -> 400
    invalid_range = await client.get(
        f"/api/v1/tasks?start_date={e_filter}&end_date={s_filter}",
        headers=auth_headers_owner,
    )
    assert invalid_range.status_code == 400
    assert invalid_range.json()["error"]["message"] == "Start date cannot be after end date."

    # Pagination: limit=2, offset=0
    p1_res = await client.get("/api/v1/tasks?limit=2&offset=0&sort_by=due_date&sort_order=asc", headers=auth_headers_owner)
    assert p1_res.status_code == 200
    assert len(p1_res.json()) == 2
    assert p1_res.json()[0]["title"] == "Range Task 1"
    assert p1_res.json()[1]["title"] == "Range Task 2"

    # Pagination: limit=2, offset=2
    p2_res = await client.get("/api/v1/tasks?limit=2&offset=2&sort_by=due_date&sort_order=asc", headers=auth_headers_owner)
    assert p2_res.status_code == 200
    assert len(p2_res.json()) >= 1
    assert p2_res.json()[0]["title"] == "Range Task 3"


# ==============================================================================
# 4. Database-Side Metrics Aggregation
# ==============================================================================


@pytest.mark.asyncio
async def test_database_side_task_metrics_aggregation(
    client: AsyncClient,
    auth_headers_owner: dict,
    test_user_owner: User,
    test_user_member: User,
    seed_tasks_test_data: dict,
):
    """Verify that get_metrics accurately computes database-side counts and respects assigned_to_id and tenant isolation."""
    data = seed_tasks_test_data
    now = datetime.now(timezone.utc)
    today_future = now.replace(hour=23, minute=50, second=0, microsecond=0)

    # 1. Overdue PENDING task (2 days ago)
    t_overdue = await client.post(
        "/api/v1/tasks",
        json={
            "title": "Overdue Pending",
            "due_date": (now - timedelta(days=2)).isoformat(),
            "status": "PENDING",
            "assigned_to_id": test_user_owner.id,
        },
        headers=auth_headers_owner,
    )
    assert t_overdue.status_code == 201

    # 2. Overdue COMPLETED task (2 days ago) -> MUST NOT count towards overdue!
    t_overdue_comp = await client.post(
        "/api/v1/tasks",
        json={
            "title": "Overdue But Completed",
            "due_date": (now - timedelta(days=2)).isoformat(),
            "status": "COMPLETED",
            "assigned_to_id": test_user_owner.id,
        },
        headers=auth_headers_owner,
    )
    assert t_overdue_comp.status_code == 201

    # 3. Due Today PENDING task (assigned to member, due later today)
    t_today = await client.post(
        "/api/v1/tasks",
        json={
            "title": "Due Today Task",
            "due_date": today_future.isoformat(),
            "status": "PENDING",
            "assigned_to_id": test_user_member.id,
        },
        headers=auth_headers_owner,
    )
    assert t_today.status_code == 201

    # 4. Upcoming IN_PROGRESS task (3 days in future, assigned to member)
    t_upcoming = await client.post(
        "/api/v1/tasks",
        json={
            "title": "Upcoming Task",
            "due_date": (now + timedelta(days=3)).isoformat(),
            "status": "IN_PROGRESS",
            "assigned_to_id": test_user_member.id,
        },
        headers=auth_headers_owner,
    )
    assert t_upcoming.status_code == 201

    # 5. Query Org A overall metrics
    metrics_res = await client.get("/api/v1/tasks/metrics", headers=auth_headers_owner)
    assert metrics_res.status_code == 200
    m = metrics_res.json()

    assert m["total_tasks"] == 4
    assert m["overdue_count"] == 1  # Only t_overdue, not t_overdue_comp
    assert m["due_today_count"] == 1  # t_today
    assert m["upcoming_count"] == 2  # t_today (due later today > now) and t_upcoming (due in 3 days)
    assert m["completed_count"] == 1

    # 6. Query metrics scoped to test_user_member only
    member_metrics_res = await client.get(
        f"/api/v1/tasks/metrics?assigned_to_id={test_user_member.id}",
        headers=auth_headers_owner,
    )
    assert member_metrics_res.status_code == 200
    mm = member_metrics_res.json()
    assert mm["total_tasks"] == 2
    assert mm["overdue_count"] == 0
    assert mm["due_today_count"] == 1
    assert mm["upcoming_count"] == 2
    assert mm["completed_count"] == 0

    # 7. Query Org B metrics -> isolated from Org A
    beta_metrics_res = await client.get("/api/v1/tasks/metrics", headers=data["auth_headers_b"])
    assert beta_metrics_res.status_code == 200
    bm = beta_metrics_res.json()
    assert bm["total_tasks"] == 1  # Only task_b created in seed
    assert bm["overdue_count"] == 0
    assert bm["upcoming_count"] == 1


# ==============================================================================
# 5. Workflow Regressions: Quick Complete, Update, Delete & Escalation
# ==============================================================================


@pytest.mark.asyncio
async def test_task_lifecycle_and_actions(
    client: AsyncClient,
    auth_headers_owner: dict,
):
    """Test 1-click completion, update, delete, and escalate-overdue routes."""
    # 1. Create a task
    create_res = await client.post(
        "/api/v1/tasks",
        json={
            "title": "Actionable Task",
            "due_date": (datetime.now(timezone.utc) - timedelta(hours=30)).isoformat(),  # >24h overdue
            "priority": "LOW",
            "status": "PENDING",
        },
        headers=auth_headers_owner,
    )
    assert create_res.status_code == 201
    task_id = create_res.json()["id"]

    # 2. Test Escalate Overdue
    esc_res = await client.post("/api/v1/tasks/escalate-overdue", headers=auth_headers_owner)
    assert esc_res.status_code == 200
    esc_data = esc_res.json()
    assert esc_data["success"] is True
    assert esc_data["escalated_count"] >= 1
    escalated_task = next((t for t in esc_data["tasks"] if t["id"] == task_id), None)
    assert escalated_task is not None
    assert escalated_task["priority"] == "URGENT"

    # 3. Test 1-click complete
    comp_res = await client.post(f"/api/v1/tasks/{task_id}/complete", headers=auth_headers_owner)
    assert comp_res.status_code == 200
    comp_data = comp_res.json()
    assert comp_data["status"] == "COMPLETED"
    assert comp_data["completed_at"] is not None
    assert comp_data["is_overdue"] is False

    # 4. Test delete
    del_res = await client.delete(f"/api/v1/tasks/{task_id}", headers=auth_headers_owner)
    assert del_res.status_code == 204

    # 5. Verify task is deleted
    get_after_del = await client.get(f"/api/v1/tasks/{task_id}", headers=auth_headers_owner)
    assert get_after_del.status_code == 404
