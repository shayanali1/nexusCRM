import pytest
import pytest_asyncio
from datetime import datetime, timezone, timedelta
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.events import CRMEvent, CRMEventType, event_dispatcher
from app.core.security import create_access_token, hash_password
from app.modules.activities.models import Activity
from app.modules.automation.models import AutomationRule, AutomationAction
from app.modules.automation.service import AutomationService
from app.modules.automation.workflows import check_and_process_overdue_deals
from app.modules.companies.models import Company
from app.modules.contacts.models import Contact
from app.modules.deals.models import Deal, DealStatus
from app.modules.notifications.models import Notification
from app.modules.organizations.models import Organization
from app.modules.pipelines.models import Pipeline, PipelineStage
from app.modules.tasks.models import Task, TaskPriority, TaskStatus, TaskType
from app.modules.users.models import User
from app.workers.automation_jobs import async_scan_overdue_deals, scan_overdue_deals_periodic
from app.workers.celery_app import celery_app


@pytest_asyncio.fixture(scope="function")
async def seed_automation_data(
    db_session: AsyncSession,
    test_org: Organization,
    test_user_owner: User,
    test_user_member: User,
):
    """Seed pipelines, stages, contacts, companies, and deals for Org A and foreign Org B."""
    base_time = datetime(2026, 3, 1, 12, 0, 0, tzinfo=timezone.utc)

    # 1. Foreign Org B
    org_b = Organization(name="Foreign Org B", slug="foreign-b", is_active=True)
    db_session.add(org_b)
    await db_session.flush()

    user_b = User(
        organization_id=org_b.id,
        email="owner@foreignb.com",
        hashed_password=hash_password("password123"),
        first_name="Victor",
        last_name="Foreign",
        role="OWNER",
        is_active=True,
    )
    db_session.add(user_b)
    await db_session.flush()

    pipe_b = Pipeline(organization_id=org_b.id, name="Pipeline B", is_default=True)
    db_session.add(pipe_b)
    await db_session.flush()

    stage_b = PipelineStage(
        organization_id=org_b.id,
        pipeline_id=pipe_b.id,
        name="Stage B",
        order=1,
        win_probability=50,
    )
    db_session.add(stage_b)
    await db_session.flush()

    deal_b = Deal(
        id="80000000-0000-0000-0000-000000000001",
        organization_id=org_b.id,
        pipeline_id=pipe_b.id,
        stage_id=stage_b.id,
        title="Org B Foreign Deal",
        value=99000.0,
        status=DealStatus.OPEN.value,
        assigned_to_id=user_b.id,
        expected_close_date=base_time - timedelta(days=5),
        created_at=base_time - timedelta(days=10),
    )
    db_session.add(deal_b)
    await db_session.flush()

    # 2. Org A Setup
    pipe_a_res = (await db_session.execute(
        select(Pipeline).where(Pipeline.organization_id == test_org.id)
    )).scalars().first()
    pipe_a_id = pipe_a_res.id

    stage_qual = (await db_session.execute(
        select(PipelineStage).where(PipelineStage.pipeline_id == pipe_a_id)
    )).scalars().first()
    s_qual_id = stage_qual.id

    stage_demo = PipelineStage(
        organization_id=test_org.id,
        pipeline_id=pipe_a_id,
        name="Technical Demo",
        order=2,
        win_probability=40,
    )
    stage_proposal = PipelineStage(
        organization_id=test_org.id,
        pipeline_id=pipe_a_id,
        name="Proposal Review",
        order=3,
        win_probability=70,
    )
    stage_won = PipelineStage(
        organization_id=test_org.id,
        pipeline_id=pipe_a_id,
        name="Closed Won",
        order=4,
        win_probability=100,
        is_won=True,
    )
    stage_lost = PipelineStage(
        organization_id=test_org.id,
        pipeline_id=pipe_a_id,
        name="Closed Lost",
        order=5,
        win_probability=0,
        is_lost=True,
    )
    db_session.add_all([stage_demo, stage_proposal, stage_won, stage_lost])
    await db_session.flush()

    comp_a = Company(organization_id=test_org.id, name="Acme Cloud Systems")
    db_session.add(comp_a)
    await db_session.flush()

    cont_a = Contact(
        organization_id=test_org.id,
        company_id=comp_a.id,
        first_name="Diana",
        last_name="Prince",
        email="diana@acmecloud.com",
    )
    db_session.add(cont_a)
    await db_session.flush()

    # Deal in Org A
    deal_a = Deal(
        id="70000000-0000-0000-0000-000000000001",
        organization_id=test_org.id,
        pipeline_id=pipe_a_id,
        stage_id=s_qual_id,
        contact_id=cont_a.id,
        company_id=comp_a.id,
        assigned_to_id=test_user_owner.id,
        title="Acme Cloud Platform License",
        value=65000.0,
        status=DealStatus.OPEN.value,
        win_probability=10,
        expected_close_date=datetime.now(timezone.utc) + timedelta(days=60),
        created_at=base_time,
    )
    db_session.add(deal_a)
    await db_session.commit()

    token_b = create_access_token(user_b.id, org_b.id, user_b.role)

    return {
        "org_b": org_b,
        "user_b": user_b,
        "token_b": token_b,
        "deal_b": deal_b,
        "stage_b": stage_b,
        "pipe_a_id": pipe_a_id,
        "s_qual_id": s_qual_id,
        "s_demo_id": stage_demo.id,
        "s_proposal_id": stage_proposal.id,
        "s_won_id": stage_won.id,
        "s_lost_id": stage_lost.id,
        "comp_a_id": comp_a.id,
        "cont_a_id": cont_a.id,
        "deal_a_id": deal_a.id,
    }


# ============================================================================
# 1. STAGE CHANGE AUTOMATION
# ============================================================================

@pytest.mark.asyncio
async def test_deal_stage_changed_triggers_automation_rule(
    client: AsyncClient,
    test_org: Organization,
    auth_headers_owner: dict,
    seed_automation_data,
):
    """When a deal enters a configured stage, dynamic automation rules matching the stage create follow-up tasks."""
    s_demo_id = seed_automation_data["s_demo_id"]
    deal_id = seed_automation_data["deal_a_id"]

    # 1. Create an AutomationRule triggered on deal.stage_changed with condition stage_id == s_demo_id
    rule_res = await client.post(
        "/api/v1/automation/rules",
        json={
            "name": "Prepare Technical Demo Task",
            "event_trigger": "deal.stage_changed",
            "conditions": [{"field": "stage_id", "operator": "equals", "value": s_demo_id}],
            "actions": [
                {
                    "action_type": "create_task",
                    "action_config": {
                        "title": "Prepare Demo Environment",
                        "description": "Configure cloud sandbox for prospect demo.",
                        "due_in_hours": 48,
                    },
                }
            ],
        },
        headers=auth_headers_owner,
    )
    assert rule_res.status_code == 201
    rule_id = rule_res.json()["id"]

    # 2. Move deal to Technical Demo stage
    move_res = await client.post(
        f"/api/v1/deals/{deal_id}/move-stage",
        json={"stage_id": s_demo_id},
        headers=auth_headers_owner,
    )
    assert move_res.status_code == 200

    # 3. Verify task was automatically created and linked to the deal
    tasks_res = await client.get(f"/api/v1/tasks?deal_id={deal_id}", headers=auth_headers_owner)
    assert tasks_res.status_code == 200
    tasks = tasks_res.json()
    assert any(t["title"] == "Prepare Demo Environment" for t in tasks)
    task = next(t for t in tasks if t["title"] == "Prepare Demo Environment")
    assert task["deal_id"] == deal_id
    assert task["status"] == TaskStatus.PENDING.value
    assert task["priority"] == TaskPriority.HIGH.value


@pytest.mark.asyncio
async def test_deal_stage_changed_unmatched_condition_skips_actions(
    client: AsyncClient,
    test_org: Organization,
    auth_headers_owner: dict,
    seed_automation_data,
):
    """Stage changes that do not match rule conditions do not trigger actions."""
    s_demo_id = seed_automation_data["s_demo_id"]
    s_proposal_id = seed_automation_data["s_proposal_id"]
    deal_id = seed_automation_data["deal_a_id"]

    # Create rule conditioned strictly on s_demo_id
    await client.post(
        "/api/v1/automation/rules",
        json={
            "name": "Demo Only Automation",
            "event_trigger": "deal.stage_changed",
            "conditions": [{"field": "stage_id", "operator": "equals", "value": s_demo_id}],
            "actions": [
                {
                    "action_type": "create_task",
                    "action_config": {"title": "Demo Exclusive Task"},
                }
            ],
        },
        headers=auth_headers_owner,
    )

    # Move deal to Proposal Review stage (does not match s_demo_id)
    move_res = await client.post(
        f"/api/v1/deals/{deal_id}/move-stage",
        json={"stage_id": s_proposal_id},
        headers=auth_headers_owner,
    )
    assert move_res.status_code == 200

    # Verify "Demo Exclusive Task" was NOT created
    tasks_res = await client.get(f"/api/v1/tasks?deal_id={deal_id}", headers=auth_headers_owner)
    assert tasks_res.status_code == 200
    tasks = tasks_res.json()
    assert not any(t["title"] == "Demo Exclusive Task" for t in tasks)


# ============================================================================
# 2. DEAL WON & DEAL LOST LIFECYCLE ACTIONS
# ============================================================================

@pytest.mark.asyncio
async def test_deal_marked_won_triggers_customer_update_and_onboarding(
    client: AsyncClient,
    test_org: Organization,
    auth_headers_owner: dict,
    seed_automation_data,
    db_session: AsyncSession,
):
    """Marking a deal WON updates contact lifecycle to CUSTOMER and creates onboarding tasks."""
    deal_id = seed_automation_data["deal_a_id"]
    s_won_id = seed_automation_data["s_won_id"]
    cont_id = seed_automation_data["cont_a_id"]

    # Move deal to won stage
    res = await client.post(
        f"/api/v1/deals/{deal_id}/move-stage",
        json={"stage_id": s_won_id},
        headers=auth_headers_owner,
    )
    assert res.status_code == 200
    assert res.json()["status"] == DealStatus.WON.value

    # Verify contact marked as CUSTOMER
    cont_res = await client.get(f"/api/v1/contacts/{cont_id}", headers=auth_headers_owner)
    assert cont_res.status_code == 200
    assert cont_res.json()["custom_fields"].get("lifecycle_stage") == "CUSTOMER"

    # Verify onboarding tasks created
    tasks_res = await client.get(f"/api/v1/tasks?deal_id={deal_id}", headers=auth_headers_owner)
    assert tasks_res.status_code == 200
    titles = [t["title"] for t in tasks_res.json()]
    assert "Kickoff Onboarding & Requirements Review" in titles
    assert "Send Customer Welcome Packet & Invoicing" in titles


@pytest.mark.asyncio
async def test_deal_marked_lost_triggers_activity_and_notification(
    client: AsyncClient,
    test_org: Organization,
    auth_headers_owner: dict,
    seed_automation_data,
):
    """Marking a deal LOST records an activity timeline item with lost_reason and notifies rep."""
    deal_id = seed_automation_data["deal_a_id"]
    s_lost_id = seed_automation_data["s_lost_id"]

    res = await client.post(
        f"/api/v1/deals/{deal_id}/move-stage",
        json={"stage_id": s_lost_id, "lost_reason": "Competitor chosen on price"},
        headers=auth_headers_owner,
    )
    assert res.status_code == 200
    assert res.json()["status"] == DealStatus.LOST.value
    assert res.json()["lost_reason"] == "Competitor chosen on price"

    # Verify activity was created
    acts_res = await client.get(f"/api/v1/activities?deal_id={deal_id}", headers=auth_headers_owner)
    assert acts_res.status_code == 200
    acts = acts_res.json()
    assert any("Deal Lost" in a["title"] for a in acts)
    lost_act = next(a for a in acts if "Deal Lost" in a["title"])
    assert "Competitor chosen on price" in lost_act["description"]

    # Verify notification created
    notifs_res = await client.get("/api/v1/notifications", headers=auth_headers_owner)
    assert notifs_res.status_code == 200
    notifs = notifs_res.json()
    assert any("Deal Lost" in n["title"] for n in notifs)


# ============================================================================
# 3. DUPLICATE PREVENTION & IDEMPOTENCY
# ============================================================================

@pytest.mark.asyncio
async def test_deal_automation_idempotency_prevents_duplicate_tasks(
    client: AsyncClient,
    test_org: Organization,
    auth_headers_owner: dict,
    seed_automation_data,
    db_session: AsyncSession,
):
    """Repeated stage changes or retried automation triggers do not create duplicate tasks."""
    s_demo_id = seed_automation_data["s_demo_id"]
    deal_id = seed_automation_data["deal_a_id"]

    # 1. Create rule
    await client.post(
        "/api/v1/automation/rules",
        json={
            "name": "Single Task Rule",
            "event_trigger": "deal.stage_changed",
            "conditions": [{"field": "stage_id", "operator": "equals", "value": s_demo_id}],
            "actions": [
                {
                    "action_type": "create_task",
                    "action_config": {"title": "Idempotent Sandbox Prep", "due_in_hours": 24},
                }
            ],
        },
        headers=auth_headers_owner,
    )

    # Move deal to s_demo_id first time
    res1 = await client.post(
        f"/api/v1/deals/{deal_id}/move-stage",
        json={"stage_id": s_demo_id},
        headers=auth_headers_owner,
    )
    assert res1.status_code == 200

    # Repeat move to same stage (simulating retry or repeated action)
    res2 = await client.post(
        f"/api/v1/deals/{deal_id}/move-stage",
        json={"stage_id": s_demo_id},
        headers=auth_headers_owner,
    )
    assert res2.status_code == 200

    # Verify exactly 1 task exists
    tasks_res = await client.get(f"/api/v1/tasks?deal_id={deal_id}", headers=auth_headers_owner)
    assert tasks_res.status_code == 200
    matching_tasks = [t for t in tasks_res.json() if t["title"] == "Idempotent Sandbox Prep"]
    assert len(matching_tasks) == 1

    # Directly re-trigger event via AutomationService (simulating Celery worker retry)
    svc = AutomationService(db_session, test_org.id)
    await svc.trigger_event("deal.stage_changed", {"deal_id": deal_id, "stage_id": s_demo_id})

    # Verify count remains exactly 1
    tasks_res_after = await client.get(f"/api/v1/tasks?deal_id={deal_id}", headers=auth_headers_owner)
    matching_tasks_after = [t for t in tasks_res_after.json() if t["title"] == "Idempotent Sandbox Prep"]
    assert len(matching_tasks_after) == 1


# ============================================================================
# 4. OVERDUE DEAL PROCESSING
# ============================================================================

@pytest.mark.asyncio
async def test_overdue_deal_detection_and_task_creation(
    client: AsyncClient,
    test_org: Organization,
    test_user_owner: User,
    auth_headers_owner: dict,
    seed_automation_data,
    db_session: AsyncSession,
):
    """Overdue deal scanner detects open deals past expected close date and creates follow-up tasks."""
    now = datetime.now(timezone.utc)
    pipe_id = seed_automation_data["pipe_a_id"]
    s_qual_id = seed_automation_data["s_qual_id"]
    s_won_id = seed_automation_data["s_won_id"]
    s_lost_id = seed_automation_data["s_lost_id"]

    # 1. Overdue Open Deal: expected_close_date in the past
    deal_overdue = Deal(
        organization_id=test_org.id,
        pipeline_id=pipe_id,
        stage_id=s_qual_id,
        title="Overdue Enterprise Deal",
        value=30000.0,
        status=DealStatus.OPEN.value,
        assigned_to_id=test_user_owner.id,
        expected_close_date=now - timedelta(days=2),
    )
    # 2. Future Open Deal: expected_close_date in the future (should NOT be processed)
    deal_future = Deal(
        organization_id=test_org.id,
        pipeline_id=pipe_id,
        stage_id=s_qual_id,
        title="Future Deal",
        value=40000.0,
        status=DealStatus.OPEN.value,
        assigned_to_id=test_user_owner.id,
        expected_close_date=now + timedelta(days=30),
    )
    # 3. Won Deal with past expected close date (should NOT be processed)
    deal_won = Deal(
        organization_id=test_org.id,
        pipeline_id=pipe_id,
        stage_id=s_won_id,
        title="Closed Won Past Deal",
        value=50000.0,
        status=DealStatus.WON.value,
        assigned_to_id=test_user_owner.id,
        expected_close_date=now - timedelta(days=10),
    )
    # 4. Lost Deal with past expected close date (should NOT be processed)
    deal_lost = Deal(
        organization_id=test_org.id,
        pipeline_id=pipe_id,
        stage_id=s_lost_id,
        title="Closed Lost Past Deal",
        value=15000.0,
        status=DealStatus.LOST.value,
        assigned_to_id=test_user_owner.id,
        expected_close_date=now - timedelta(days=10),
    )
    # 5. Open Deal with NO expected close date (should NOT be processed)
    deal_no_date = Deal(
        organization_id=test_org.id,
        pipeline_id=pipe_id,
        stage_id=s_qual_id,
        title="Undated Deal",
        value=20000.0,
        status=DealStatus.OPEN.value,
        assigned_to_id=test_user_owner.id,
        expected_close_date=None,
    )
    db_session.add_all([deal_overdue, deal_future, deal_won, deal_lost, deal_no_date])
    await db_session.commit()

    # Run overdue deals check for test_org
    processed = await check_and_process_overdue_deals(db_session, test_org.id)
    processed_titles = [d.title for d in processed]

    # Only deal_overdue was processed
    assert "Overdue Enterprise Deal" in processed_titles
    assert "Future Deal" not in processed_titles
    assert "Closed Won Past Deal" not in processed_titles
    assert "Closed Lost Past Deal" not in processed_titles
    assert "Undated Deal" not in processed_titles

    # Verify task was created for overdue deal
    tasks_res = await client.get(f"/api/v1/tasks?deal_id={deal_overdue.id}", headers=auth_headers_owner)
    assert tasks_res.status_code == 200
    tasks = tasks_res.json()
    assert len(tasks) == 1
    assert "Review Overdue Deal" in tasks[0]["title"]
    assert tasks[0]["priority"] == TaskPriority.HIGH.value

    # IDEMPOTENCY: Re-run scan; deal_overdue should not be re-processed or get duplicate task
    processed_again = await check_and_process_overdue_deals(db_session, test_org.id)
    assert not any(d.id == deal_overdue.id for d in processed_again)

    tasks_res2 = await client.get(f"/api/v1/tasks?deal_id={deal_overdue.id}", headers=auth_headers_owner)
    assert len(tasks_res2.json()) == 1


# ============================================================================
# 5. TENANT ISOLATION & ROLLBACK SAFETY
# ============================================================================

@pytest.mark.asyncio
async def test_automation_tenant_isolation(
    client: AsyncClient,
    test_org: Organization,
    auth_headers_owner: dict,
    seed_automation_data,
    db_session: AsyncSession,
):
    """Automation rules in Org A cannot touch or create tasks for Org B deals."""
    deal_b_id = seed_automation_data["deal_b"].id
    org_b = seed_automation_data["org_b"]

    # 1. Attempt to execute an automation in Org A referencing Org B's deal_id
    svc_a = AutomationService(db_session, test_org.id)
    # create_task action with foreign deal_b_id should be rejected
    await svc_a._execute_action(
        "create_task",
        {"title": "Illicit Cross Tenant Task", "deal_id": deal_b_id},
        {"deal_id": deal_b_id},
    )

    # Verify NO task was created in Org A or Org B with that title
    stmt = select(Task).where(Task.title == "Illicit Cross Tenant Task")
    res = (await db_session.execute(stmt)).scalars().all()
    assert len(res) == 0

    # 2. Periodic overdue deals scan processes each organization in its own boundary
    scan_res = await async_scan_overdue_deals(db_session)
    assert scan_res["organizations_processed"] >= 2
    assert org_b.id in scan_res["details"]
    assert test_org.id in scan_res["details"]
    assert scan_res["details"][org_b.id]["status"] == "success"
    assert scan_res["details"][test_org.id]["status"] == "success"


@pytest.mark.asyncio
async def test_failed_update_does_not_trigger_automation(
    client: AsyncClient,
    test_org: Organization,
    auth_headers_owner: dict,
    seed_automation_data,
):
    """When a deal update or move fails validation, no automation event is triggered."""
    deal_id = seed_automation_data["deal_a_id"]
    foreign_stage_id = seed_automation_data["stage_b"].id

    # Create a rule triggered on stage_changed
    await client.post(
        "/api/v1/automation/rules",
        json={
            "name": "Never Trigger Rule",
            "event_trigger": "deal.stage_changed",
            "actions": [
                {
                    "action_type": "create_task",
                    "action_config": {"title": "Should Never Exist Task"},
                }
            ],
        },
        headers=auth_headers_owner,
    )

    # Attempt to move deal to a foreign stage in Org B (should fail with 404 or 400)
    failed_res = await client.post(
        f"/api/v1/deals/{deal_id}/move-stage",
        json={"stage_id": foreign_stage_id},
        headers=auth_headers_owner,
    )
    assert failed_res.status_code in (400, 404)

    # Verify task was NOT created
    tasks_res = await client.get(f"/api/v1/tasks?deal_id={deal_id}", headers=auth_headers_owner)
    assert tasks_res.status_code == 200
    assert not any(t["title"] == "Should Never Exist Task" for t in tasks_res.json())


def test_celery_overdue_deals_task_registration():
    """Verify overdue deal scanner Celery task and beat schedule registration."""
    registered_tasks = celery_app.tasks.keys()
    assert "app.workers.automation_jobs.scan_overdue_deals_periodic" in registered_tasks
    assert "scan-overdue-deals-hourly" in celery_app.conf.beat_schedule
    sched_entry = celery_app.conf.beat_schedule["scan-overdue-deals-hourly"]
    assert sched_entry["task"] == "app.workers.automation_jobs.scan_overdue_deals_periodic"
    assert sched_entry["schedule"] == 3600.0
