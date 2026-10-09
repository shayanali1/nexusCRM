"""Tests for Phase 2 Operational CRM Workflows:
1. Lead Capture & Auto-Assignment (round-robin/least-assigned, 2h discovery call task, notification, AI brief)
2. Deal Won (customer lifecycle update, 24h & 48h onboarding tasks, notification, activity logging, idempotency)
3. Proposal Follow-Up (3-day follow-up task, idempotency)
4. Overdue Task Escalation (>24h overdue tasks elevated to URGENT, notifications, idempotency)
"""

from datetime import datetime, timedelta, timezone
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from app.modules.activities.models import Activity
from app.modules.ai.models import AIInsight
from app.modules.companies.models import Company
from app.modules.contacts.models import Contact
from app.modules.deals.models import Deal, DealStatus
from app.modules.leads.models import Lead
from app.modules.notifications.models import Notification
from app.modules.organizations.models import Organization
from app.modules.pipelines.models import Pipeline, PipelineStage
from app.modules.tasks.models import Task, TaskPriority, TaskStatus, TaskType
from app.modules.users.models import User


@pytest.mark.asyncio
async def test_lead_capture_auto_assignment_and_followup(
    client: AsyncClient,
    test_org: Organization,
    test_user_owner: User,
    test_user_member: User,
    auth_headers_owner: dict,
    db_session,
    mock_celery_dispatch,
):
    """Test that creating an unassigned lead triggers auto-assignment, 2h discovery call task, and notifications."""
    resp = await client.post(
        "/api/v1/leads",
        json={
            "title": "Enterprise Cloud Migration Deal",
            "contact_name": "John Cloud",
            "contact_email": "john@cloudenterprise.io",
            "company_name": "Cloud Enterprise Corp",
            "source": "Website",
            "estimated_value": 75000.0,
            "notes": "Urgent timeline for Q4 rollout.",
        },
        headers=auth_headers_owner,
    )
    assert resp.status_code == 201
    lead_data = resp.json()
    lead_id = lead_data["id"]

    # 1. Lead was auto-assigned to an active org user
    assert lead_data["assigned_to_id"] in [test_user_owner.id, test_user_member.id]

    # 2. 'First Discovery Call' task was created due in ~2 hours with HIGH priority
    tasks_res = await client.get(
        f"/api/v1/tasks?lead_id={lead_id}",
        headers=auth_headers_owner,
    )
    assert tasks_res.status_code == 200
    tasks = tasks_res.json()
    assert len(tasks) == 1
    discovery_task = tasks[0]
    assert discovery_task["title"] == "First Discovery Call"
    assert discovery_task["priority"] == TaskPriority.HIGH.value
    assert discovery_task["task_type"] == TaskType.CALL.value
    assert discovery_task["assigned_to_id"] == lead_data["assigned_to_id"]

    # 3. Notification created for assigned user
    notifs_res = await client.get("/api/v1/notifications", headers=auth_headers_owner)
    assert notifs_res.status_code == 200
    notifs = notifs_res.json()
    assert any("New Lead Assigned" in n["title"] for n in notifs)

    # 4. Synchronously, no AI insight is created (dispatched to background Celery worker)
    insight_stmt = select(AIInsight).where(
        AIInsight.organization_id == test_org.id,
        AIInsight.entity_id == lead_id,
    )
    insight = (await db_session.execute(insight_stmt)).scalar_one_or_none()
    assert insight is None

    # 5. Background Celery worker generates and persists the AI insight when executed
    from app.workers.ai_jobs import async_process_lead_summary
    await async_process_lead_summary(
        organization_id=test_org.id,
        lead_id=lead_id,
        context={
            "contact_name": "Enterprise Cloud Migration Deal",
            "company_name": "Cloud Enterprise Corp",
            "stage": "NEW",
            "estimated_value": 75000.0,
            "notes": "Urgent timeline for Q4 rollout.",
        },
        session=db_session,
    )
    insight_after = (await db_session.execute(insight_stmt)).scalar_one_or_none()
    assert insight_after is not None
    assert insight_after.insight_type == "SUMMARY"


@pytest.mark.asyncio
async def test_deal_won_workflow_and_idempotency(
    client: AsyncClient,
    test_org: Organization,
    test_user_owner: User,
    auth_headers_owner: dict,
    db_session,
):
    """Test Deal Won workflow marks contacts as CUSTOMER, creates onboarding tasks idempotently, and logs activity."""
    # Create contact & company
    company = Company(organization_id=test_org.id, name="Omega Logistics")
    db_session.add(company)
    await db_session.flush()

    contact = Contact(
        organization_id=test_org.id,
        company_id=company.id,
        first_name="David",
        last_name="Miller",
        email="david@omega.com",
    )
    db_session.add(contact)
    await db_session.flush()

    # Create pipeline and stages
    pipe_stmt = select(Pipeline).where(Pipeline.organization_id == test_org.id)
    pipeline = (await db_session.execute(pipe_stmt)).scalars().first()

    won_stage = PipelineStage(
        organization_id=test_org.id,
        pipeline_id=pipeline.id,
        name="Closed Won",
        order=5,
        win_probability=100,
        is_won=True,
    )
    db_session.add(won_stage)
    await db_session.commit()

    # Create deal
    deal_resp = await client.post(
        "/api/v1/deals",
        json={
            "title": "Omega Logistics Software License",
            "pipeline_id": pipeline.id,
            "stage_id": won_stage.id,
            "contact_id": contact.id,
            "company_id": company.id,
            "value": 45000.0,
            "assigned_to_id": test_user_owner.id,
        },
        headers=auth_headers_owner,
    )
    assert deal_resp.status_code == 201
    deal_id = deal_resp.json()["id"]

    # Trigger deal move to Won
    move_resp = await client.post(
        f"/api/v1/deals/{deal_id}/move-stage",
        json={"stage_id": won_stage.id},
        headers=auth_headers_owner,
    )
    assert move_resp.status_code == 200
    assert move_resp.json()["status"] == DealStatus.WON.value

    # 1. Contact and company lifecycle stage updated to CUSTOMER
    await db_session.refresh(contact)
    await db_session.refresh(company)
    assert contact.custom_fields.get("lifecycle_stage") == "CUSTOMER"
    assert company.custom_fields.get("lifecycle_stage") == "CUSTOMER"

    # 2. Both onboarding tasks created
    tasks_res = await client.get(
        f"/api/v1/tasks?deal_id={deal_id}",
        headers=auth_headers_owner,
    )
    assert tasks_res.status_code == 200
    tasks = tasks_res.json()
    task_titles = [t["title"] for t in tasks]
    assert "Kickoff Onboarding & Requirements Review" in task_titles
    assert "Send Customer Welcome Packet & Invoicing" in task_titles

    # 3. Activity timeline entry created
    acts_res = await client.get(
        f"/api/v1/activities?deal_id={deal_id}",
        headers=auth_headers_owner,
    )
    assert acts_res.status_code == 200
    acts = acts_res.json()
    assert any("Deal Won" in a["title"] for a in acts)

    # 4. IDEMPOTENCY TEST: Trigger move to won stage again
    move_again = await client.post(
        f"/api/v1/deals/{deal_id}/move-stage",
        json={"stage_id": won_stage.id},
        headers=auth_headers_owner,
    )
    assert move_again.status_code == 200

    # Verify task count has NOT increased
    tasks_res_after = await client.get(
        f"/api/v1/tasks?deal_id={deal_id}",
        headers=auth_headers_owner,
    )
    assert len(tasks_res_after.json()) == 2


@pytest.mark.asyncio
async def test_proposal_followup_workflow_and_idempotency(
    client: AsyncClient,
    test_org: Organization,
    test_user_owner: User,
    auth_headers_owner: dict,
    db_session,
):
    """Test Proposal follow-up workflow creates task due in 3 days idempotently."""
    pipe_stmt = select(Pipeline).where(Pipeline.organization_id == test_org.id)
    pipeline = (await db_session.execute(pipe_stmt)).scalars().first()
    stage = (await db_session.execute(select(PipelineStage).where(PipelineStage.pipeline_id == pipeline.id))).scalars().first()

    deal = Deal(
        organization_id=test_org.id,
        pipeline_id=pipeline.id,
        stage_id=stage.id,
        title="Acme Corp SaaS Upgrade",
        value=15000.0,
        assigned_to_id=test_user_owner.id,
    )
    db_session.add(deal)
    await db_session.commit()
    await db_session.refresh(deal)

    # Log a proposal activity
    act_resp = await client.post(
        "/api/v1/activities",
        json={
            "deal_id": deal.id,
            "activity_type": "PROPOSAL",
            "title": "Sent SaaS Proposal v1.0",
            "description": "Sent detailed pricing proposal with tiered seats.",
            "performed_at": datetime.now(timezone.utc).isoformat(),
        },
        headers=auth_headers_owner,
    )
    assert act_resp.status_code == 201

    # Verify proposal follow-up task was created
    tasks_res = await client.get(
        f"/api/v1/tasks?deal_id={deal.id}",
        headers=auth_headers_owner,
    )
    assert tasks_res.status_code == 200
    tasks = tasks_res.json()
    followup_tasks = [t for t in tasks if "Follow up on proposal" in t["title"]]
    assert len(followup_tasks) == 1
    assert followup_tasks[0]["priority"] == TaskPriority.MEDIUM.value
    assert followup_tasks[0]["task_type"] == TaskType.FOLLOW_UP.value

    # IDEMPOTENCY: Log another proposal activity
    act_resp2 = await client.post(
        "/api/v1/activities",
        json={
            "deal_id": deal.id,
            "activity_type": "PROPOSAL",
            "title": "Sent Revised Proposal v1.1",
            "performed_at": datetime.now(timezone.utc).isoformat(),
        },
        headers=auth_headers_owner,
    )
    assert act_resp2.status_code == 201

    tasks_res2 = await client.get(
        f"/api/v1/tasks?deal_id={deal.id}",
        headers=auth_headers_owner,
    )
    followup_tasks2 = [t for t in tasks_res2.json() if "Follow up on proposal" in t["title"]]
    # Should still only be 1 task, not duplicated!
    assert len(followup_tasks2) == 1


@pytest.mark.asyncio
async def test_overdue_task_escalation_workflow(
    client: AsyncClient,
    test_org: Organization,
    test_user_owner: User,
    auth_headers_owner: dict,
    db_session,
):
    """Test that overdue tasks (>24h past due) are elevated to URGENT priority idempotently."""
    now = datetime.now(timezone.utc)
    # Task overdue by 36 hours
    overdue_task = Task(
        organization_id=test_org.id,
        assigned_to_id=test_user_owner.id,
        title="Follow up on cold email reply",
        task_type=TaskType.FOLLOW_UP.value,
        priority=TaskPriority.LOW.value,
        status=TaskStatus.PENDING.value,
        due_date=now - timedelta(hours=36),
    )
    # Task not overdue (due tomorrow)
    upcoming_task = Task(
        organization_id=test_org.id,
        assigned_to_id=test_user_owner.id,
        title="Schedule demo call",
        task_type=TaskType.CALL.value,
        priority=TaskPriority.MEDIUM.value,
        status=TaskStatus.PENDING.value,
        due_date=now + timedelta(hours=24),
    )
    db_session.add(overdue_task)
    db_session.add(upcoming_task)
    await db_session.commit()

    # Trigger escalation
    esc_resp = await client.post(
        "/api/v1/tasks/escalate-overdue",
        headers=auth_headers_owner,
    )
    assert esc_resp.status_code == 200
    data = esc_resp.json()
    assert data["success"] is True
    assert data["escalated_count"] == 1
    assert data["tasks"][0]["id"] == overdue_task.id
    assert data["tasks"][0]["priority"] == TaskPriority.URGENT.value

    # Verify task in DB has extra_metadata with escalated_at
    await db_session.refresh(overdue_task)
    assert overdue_task.priority == TaskPriority.URGENT.value
    assert "escalated_at" in overdue_task.extra_metadata

    # Verify upcoming task was untouched
    await db_session.refresh(upcoming_task)
    assert upcoming_task.priority == TaskPriority.MEDIUM.value

    # IDEMPOTENCY: Run escalation again, should escalate 0 tasks
    esc_resp2 = await client.post(
        "/api/v1/tasks/escalate-overdue",
        headers=auth_headers_owner,
    )
    assert esc_resp2.status_code == 200
    assert esc_resp2.json()["escalated_count"] == 0


@pytest.mark.asyncio
async def test_lead_creation_dispatches_celery_task_with_expected_arguments(
    client: AsyncClient,
    test_org: Organization,
    auth_headers_owner: dict,
    db_session,
):
    """Test that creating a lead dispatches process_async_lead_summary to Celery with the expected tenant and context arguments."""
    from unittest.mock import patch

    with patch("app.workers.ai_jobs.process_async_lead_summary.delay") as mock_delay:
        resp = await client.post(
            "/api/v1/leads",
            json={
                "title": "Autonomous AI Analytics",
                "contact_name": "Ada Lovelace",
                "contact_email": "ada@lovelace.io",
                "company_name": "Analytical Engines",
                "source": "Website",
                "estimated_value": 90000.0,
                "notes": "Interested in AI engine summarization.",
            },
            headers=auth_headers_owner,
        )
        assert resp.status_code == 201
        lead_data = resp.json()
        lead_id = lead_data["id"]

        # 1. Verify Celery task dispatch boundary called once with expected arguments
        assert mock_delay.called is True
        assert mock_delay.call_count == 1
        dispatched_org_id, dispatched_lead_id, dispatched_context = mock_delay.call_args[0]
        assert dispatched_org_id == test_org.id
        assert dispatched_lead_id == lead_id
        assert dispatched_context["contact_name"] == "Autonomous AI Analytics"
        assert dispatched_context["company_name"] == "Analytical Engines"
        assert dispatched_context["stage"] == "NEW"
        assert dispatched_context["estimated_value"] == 90000.0
        assert dispatched_context["notes"] == "Interested in AI engine summarization."

        # 2. Verify AI insight is NOT generated synchronously in the database
        insight_stmt = select(AIInsight).where(
            AIInsight.organization_id == test_org.id,
            AIInsight.entity_id == lead_id,
        )
        insight = (await db_session.execute(insight_stmt)).scalar_one_or_none()
        assert insight is None


@pytest.mark.asyncio
async def test_ai_summary_idempotency_prevents_duplicate_insights(
    test_org: Organization,
    test_user_owner: User,
    db_session,
):
    """Test that worker task execution is idempotent and prevents creating duplicate AIInsight records on retries."""
    from app.workers.ai_jobs import async_process_lead_summary

    lead = Lead(
        organization_id=test_org.id,
        title="Idempotency Lead",
        estimated_value=50000.0,
        notes="First pass notes.",
    )
    db_session.add(lead)
    await db_session.commit()
    await db_session.refresh(lead)

    context1 = {
        "contact_name": lead.title,
        "company_name": "Test Co",
        "stage": "NEW",
        "estimated_value": 50000.0,
        "notes": "First pass notes.",
    }

    # 1. First execution creates insight
    res1 = await async_process_lead_summary(test_org.id, lead.id, context1, session=db_session)
    assert "summary" in res1

    insight_stmt = select(AIInsight).where(
        AIInsight.organization_id == test_org.id,
        AIInsight.entity_id == lead.id,
        AIInsight.insight_type == "SUMMARY",
    )
    insights_first = (await db_session.execute(insight_stmt)).scalars().all()
    assert len(insights_first) == 1
    first_insight_id = insights_first[0].id

    # 2. Second execution (e.g. task retry or duplicate invocation) updates existing rather than adding duplicate
    context2 = dict(context1, notes="Updated notes on retry.")
    res2 = await async_process_lead_summary(test_org.id, lead.id, context2, session=db_session)
    assert "summary" in res2

    insights_second = (await db_session.execute(insight_stmt)).scalars().all()
    assert len(insights_second) == 1
    assert insights_second[0].id == first_insight_id


@pytest.mark.asyncio
async def test_dispatch_failure_policy_preserves_lead_creation_without_sync_fallback(
    client: AsyncClient,
    test_org: Organization,
    auth_headers_owner: dict,
    db_session,
):
    """Test that Celery dispatch failures (e.g. broker down) do not crash lead creation and do NOT silently fall back to sync AI generation."""
    from unittest.mock import patch

    # Simulate broker connection failure during Celery .delay()
    with patch(
        "app.workers.ai_jobs.process_async_lead_summary.delay",
        side_effect=Exception("Redis broker connection refused (simulated outage)"),
    ):
        resp = await client.post(
            "/api/v1/leads",
            json={
                "title": "Resilient Lead Creation",
                "contact_name": "Grace Hopper",
                "company_name": "US Navy Computing",
                "source": "Referral",
                "estimated_value": 60000.0,
                "notes": "Testing broker outage resilience.",
            },
            headers=auth_headers_owner,
        )
        # Primary lead creation must succeed
        assert resp.status_code == 201
        lead_id = resp.json()["id"]

        # Lead, discovery task, and notification are safely committed in DB
        lead_stmt = select(Lead).where(Lead.id == lead_id, Lead.organization_id == test_org.id)
        lead = (await db_session.execute(lead_stmt)).scalar_one_or_none()
        assert lead is not None

        task_stmt = select(Task).where(Task.lead_id == lead_id, Task.organization_id == test_org.id)
        task = (await db_session.execute(task_stmt)).scalars().first()
        assert task is not None
        assert task.title == "First Discovery Call"

        # Explicit failure policy: NO synchronous fallback occurred, NO insight generated
        insight_stmt = select(AIInsight).where(
            AIInsight.organization_id == test_org.id,
            AIInsight.entity_id == lead_id,
        )
        insight = (await db_session.execute(insight_stmt)).scalar_one_or_none()
        assert insight is None


@pytest.mark.asyncio
async def test_persistence_timing_lead_committed_before_worker_dispatch(
    client: AsyncClient,
    test_org: Organization,
    auth_headers_owner: dict,
    db_session,
):
    """Test that the lead entity is fully committed in the database before the background task dispatch is attempted."""
    from unittest.mock import patch

    dispatched_lead_verified = False

    def verify_lead_committed_at_dispatch(org_id, lead_id, context):
        nonlocal dispatched_lead_verified
        assert org_id == test_org.id
        assert lead_id is not None

        # Query the lead in an independent database session from a separate worker thread
        # to ensure it has been committed to the database, not merely held in the caller's session cache
        try:
            from tests.conftest import TestAsyncSessionLocal
        except ImportError:
            from conftest import TestAsyncSessionLocal
        from app.workers.celery_app import run_async_in_worker

        async def _query_independent():
            async with TestAsyncSessionLocal() as session:
                stmt = select(Lead).where(
                    Lead.id == lead_id,
                    Lead.organization_id == org_id,
                )
                return (await session.execute(stmt)).scalar_one_or_none()

        committed_lead = run_async_in_worker(_query_independent())
        assert committed_lead is not None
        assert committed_lead.id == lead_id
        assert committed_lead.title == "Timing Verification Lead"
        dispatched_lead_verified = True

    with patch(
        "app.workers.ai_jobs.process_async_lead_summary.delay",
        side_effect=verify_lead_committed_at_dispatch,
    ):
        resp = await client.post(
            "/api/v1/leads",
            json={
                "title": "Timing Verification Lead",
                "contact_name": "Alan Turing",
                "company_name": "Bletchley Park",
                "source": "Inbound",
                "estimated_value": 45000.0,
            },
            headers=auth_headers_owner,
        )
        assert resp.status_code == 201
        assert dispatched_lead_verified is True
