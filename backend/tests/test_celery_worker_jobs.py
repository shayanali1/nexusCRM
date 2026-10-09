"""Tests for Celery asynchronous workers:
1. process_async_lead_summary (generates AI lead summary and persists AIInsight)
2. process_csv_import (asynchronously processes batch ingestion)
3. dispatch_event_automation (asynchronous event evaluation)
4. Worker Celery registration and tenant isolation
"""

from datetime import datetime, timedelta, timezone
import io
import uuid
import pytest
from sqlalchemy import select
from app.core.exceptions import NotFoundException
from app.modules.ai.models import AIInsight
from app.modules.imports.models import ImportJob
from app.modules.imports.service import ImportService
from app.modules.leads.models import Lead
from app.modules.notifications.models import Notification
from app.modules.organizations.models import Organization
from app.modules.tasks.models import Task, TaskPriority, TaskStatus
from app.modules.users.models import User
from app.workers.ai_jobs import async_process_lead_summary, process_async_lead_summary
from app.workers.automation_jobs import (
    async_dispatch_automation,
    async_scan_and_escalate_overdue_tasks,
    dispatch_event_automation,
    scan_overdue_tasks_periodic,
)
from app.workers.celery_app import celery_app
from app.workers.import_jobs import async_process_csv_import, process_csv_import


@pytest.mark.asyncio
async def test_worker_ai_lead_summary_execution(
    test_org: Organization,
    test_user_owner: User,
    db_session,
):
    """Test lead summary generation and AI insight database persistence with tenant isolation."""
    lead = Lead(
        organization_id=test_org.id,
        title="Global FinTech Expansion",
        estimated_value=120000.0,
        notes="Evaluating enterprise multi-currency solutions.",
    )
    db_session.add(lead)
    await db_session.commit()
    await db_session.refresh(lead)

    context = {
        "contact_name": "Jane Doe",
        "company_name": "FinTech Corp",
        "stage": "Qualified",
        "estimated_value": 120000.0,
        "notes": "Looking for rapid rollout.",
    }

    res = await async_process_lead_summary(
        organization_id=test_org.id,
        lead_id=lead.id,
        context=context,
        session=db_session,
    )

    assert "summary" in res
    assert "sentiment" in res

    # Verify AI insight created in database
    insight_stmt = select(AIInsight).where(
        AIInsight.organization_id == test_org.id,
        AIInsight.entity_id == lead.id,
    )
    insight = (await db_session.execute(insight_stmt)).scalar_one_or_none()
    assert insight is not None
    assert insight.insight_type == "SUMMARY"


@pytest.mark.asyncio
async def test_worker_ai_lead_summary_nonexistent_lead_rejected(
    test_org: Organization,
    db_session,
):
    """Test worker rejects nonexistent lead ID with NotFoundException and creates zero insights."""
    nonexistent_id = str(uuid.uuid4())
    context = {"contact_name": "Ghost Lead"}

    with pytest.raises(NotFoundException) as exc_info:
        await async_process_lead_summary(
            organization_id=test_org.id,
            lead_id=nonexistent_id,
            context=context,
            session=db_session,
        )

    assert "not found" in str(exc_info.value).lower()

    # Verify no insights exist
    insight_stmt = select(AIInsight).where(AIInsight.entity_id == nonexistent_id)
    insights = (await db_session.execute(insight_stmt)).scalars().all()
    assert len(insights) == 0


@pytest.mark.asyncio
async def test_worker_ai_lead_summary_cross_tenant_lead_rejected(
    test_org: Organization,
    db_session,
):
    """Test worker rejects cross-tenant lead ID when requested under a different organization."""
    # Create Organization B
    org_b = Organization(name="Organization Beta Cross Tenant", slug="org-beta-cross")
    db_session.add(org_b)
    await db_session.flush()

    # Create Lead belonging strictly to Organization B
    lead_b = Lead(
        organization_id=org_b.id,
        title="Beta Confidential Lead",
        estimated_value=85000.0,
    )
    db_session.add(lead_b)
    await db_session.commit()
    await db_session.refresh(lead_b)

    # Attempt to process Lead B under Organization A (test_org)
    context = {"contact_name": "Intruder Query"}
    with pytest.raises(NotFoundException) as exc_info:
        await async_process_lead_summary(
            organization_id=test_org.id,
            lead_id=lead_b.id,
            context=context,
            session=db_session,
        )

    assert "not found" in str(exc_info.value).lower()

    # Verify zero insights created for this lead under either organization
    insight_stmt = select(AIInsight).where(AIInsight.entity_id == lead_b.id)
    insights = (await db_session.execute(insight_stmt)).scalars().all()
    assert len(insights) == 0


@pytest.mark.asyncio
async def test_worker_ai_lead_summary_sequential_retry_idempotent(
    test_org: Organization,
    db_session,
):
    """Test repeated sequential worker task executions update existing insight rather than duplicating."""
    lead = Lead(
        organization_id=test_org.id,
        title="Sequential Retry Lead",
        estimated_value=60000.0,
        notes="First attempt notes",
    )
    db_session.add(lead)
    await db_session.commit()
    await db_session.refresh(lead)

    context1 = {
        "contact_name": lead.title,
        "stage": "NEW",
        "estimated_value": 60000.0,
        "notes": "First attempt notes",
    }

    # 1. First execution
    res1 = await async_process_lead_summary(
        organization_id=test_org.id,
        lead_id=lead.id,
        context=context1,
        session=db_session,
    )
    assert "summary" in res1

    insight_stmt = select(AIInsight).where(
        AIInsight.organization_id == test_org.id,
        AIInsight.entity_id == lead.id,
        AIInsight.insight_type == "SUMMARY",
    )
    insights_first = (await db_session.execute(insight_stmt)).scalars().all()
    assert len(insights_first) == 1
    first_insight_id = insights_first[0].id

    # 2. Sequential retry execution with updated context
    context2 = dict(context1, notes="Updated retry notes")
    res2 = await async_process_lead_summary(
        organization_id=test_org.id,
        lead_id=lead.id,
        context=context2,
        session=db_session,
    )
    assert "summary" in res2

    insights_second = (await db_session.execute(insight_stmt)).scalars().all()
    assert len(insights_second) == 1
    assert insights_second[0].id == first_insight_id


@pytest.mark.asyncio
async def test_worker_csv_import_execution(
    test_org: Organization,
    test_user_owner: User,
    db_session,
):
    """Test process_csv_import worker task processes file with isolated session."""
    csv_content = (
        "Name,Email,Phone\n"
        "Elena Rostova,elena@example.com,555-4040\n"
        "Marcus Vance,marcus@example.com,555-5050\n"
    )

    service = ImportService(db_session, test_org.id)
    job, _, _, total_rows = await service.create_upload_job(
        user_id=test_user_owner.id,
        file_name="worker_contacts.csv",
        file_content=csv_content.encode("utf-8"),
        entity_type="contacts",
    )

    mapping = {"Name": "name", "Email": "email", "Phone": "phone"}

    res = await async_process_csv_import(
        import_job_id=job.id,
        organization_id=test_org.id,
        mapping=mapping,
        session=db_session,
    )

    assert res["status"] == "COMPLETED"
    assert res["successful_rows"] == 2

    # Refresh job in session
    await db_session.refresh(job)
    assert job.status == "COMPLETED"
    assert job.successful_rows == 2


@pytest.mark.asyncio
async def test_worker_automation_event_dispatch(
    test_org: Organization,
    test_user_owner: User,
    db_session,
):
    """Test async_dispatch_automation worker processes event successfully."""
    res = await async_dispatch_automation(
        organization_id=test_org.id,
        event_trigger="task.overdue",
        entity_type="task",
        entity_id="task-12345",
        payload={"task_id": "task-12345"},
        session=db_session,
    )

    assert res["status"] == "processed"
    assert res["organization_id"] == test_org.id


def test_celery_task_registration():
    """Verify Celery task registration and configuration."""
    registered_tasks = celery_app.tasks.keys()
    assert "app.workers.ai_jobs.process_async_lead_summary" in registered_tasks
    assert "app.workers.import_jobs.process_csv_import" in registered_tasks
    assert "app.workers.automation_jobs.dispatch_event_automation" in registered_tasks
    assert "app.workers.automation_jobs.scan_overdue_tasks_periodic" in registered_tasks

    # Verify Celery Beat schedule registration
    assert "scan-overdue-tasks-hourly" in celery_app.conf.beat_schedule
    sched_entry = celery_app.conf.beat_schedule["scan-overdue-tasks-hourly"]
    assert sched_entry["task"] == "app.workers.automation_jobs.scan_overdue_tasks_periodic"
    assert sched_entry["schedule"] == 3600.0


@pytest.mark.asyncio
async def test_periodic_overdue_task_scheduler_execution_and_tenant_isolation(
    test_org: Organization,
    test_user_owner: User,
    db_session,
):
    """Test periodic scheduler scans active orgs, escalates overdue tasks, and ignores inactive orgs."""
    now = datetime.now(timezone.utc)
    overdue_time = now - timedelta(hours=30)
    org_a_id = test_org.id

    # 1. Organization A (test_org, active) has an overdue task
    task_a = Task(
        organization_id=org_a_id,
        assigned_to_id=test_user_owner.id,
        title="Org A Overdue Task",
        priority=TaskPriority.MEDIUM.value,
        status=TaskStatus.PENDING.value,
        due_date=overdue_time,
    )
    db_session.add(task_a)

    # 2. Organization B (active) has an overdue task
    org_b = Organization(name="Active Org Beta", slug="active-org-beta", is_active=True)
    db_session.add(org_b)
    await db_session.flush()
    org_b_id = org_b.id

    user_b = User(
        organization_id=org_b_id,
        email="owner@activebeta.com",
        hashed_password="hashed_pw_test",
        first_name="Beta",
        last_name="Owner",
        role="OWNER",
        is_active=True,
    )
    db_session.add(user_b)
    await db_session.flush()

    task_b = Task(
        organization_id=org_b_id,
        assigned_to_id=user_b.id,
        title="Org B Overdue Task",
        priority=TaskPriority.MEDIUM.value,
        status=TaskStatus.PENDING.value,
        due_date=overdue_time,
    )
    db_session.add(task_b)

    # 3. Organization C (INACTIVE) has an overdue task
    org_c = Organization(name="Inactive Org Gamma", slug="inactive-org-gamma", is_active=False)
    db_session.add(org_c)
    await db_session.flush()
    org_c_id = org_c.id

    task_c = Task(
        organization_id=org_c_id,
        title="Org C Inactive Overdue Task",
        priority=TaskPriority.MEDIUM.value,
        status=TaskStatus.PENDING.value,
        due_date=overdue_time,
    )
    db_session.add(task_c)
    await db_session.commit()

    task_a_id = task_a.id
    task_b_id = task_b.id
    task_c_id = task_c.id

    # 4. Run scheduler
    res = await async_scan_and_escalate_overdue_tasks(session=db_session)
    assert res["total_escalated"] >= 2
    assert org_a_id in res["details"]
    assert org_b_id in res["details"]
    assert org_c_id not in res["details"]  # Inactive org excluded

    # Verify Task A escalated
    await db_session.refresh(task_a)
    assert task_a.priority == TaskPriority.URGENT.value
    assert task_a.extra_metadata.get("escalated_at") is not None

    # Verify Task B escalated
    await db_session.refresh(task_b)
    assert task_b.priority == TaskPriority.URGENT.value
    assert task_b.extra_metadata.get("escalated_at") is not None

    # Verify Task C NOT escalated
    await db_session.refresh(task_c)
    assert task_c.priority == TaskPriority.MEDIUM.value
    assert task_c.extra_metadata is None or task_c.extra_metadata.get("escalated_at") is None

    # Verify tenant boundary on created notifications
    notifs_a = (await db_session.execute(
        select(Notification).where(Notification.organization_id == org_a_id)
    )).scalars().all()
    assert any(n.link == f"/tasks/{task_a_id}" for n in notifs_a)
    assert all(n.organization_id == org_a_id for n in notifs_a)

    notifs_b = (await db_session.execute(
        select(Notification).where(Notification.organization_id == org_b_id)
    )).scalars().all()
    assert any(n.link == f"/tasks/{task_b_id}" for n in notifs_b)
    assert all(n.organization_id == org_b_id for n in notifs_b)


@pytest.mark.asyncio
async def test_periodic_overdue_task_scheduler_idempotency_prevents_duplicate_escalations(
    test_org: Organization,
    test_user_owner: User,
    db_session,
):
    """Test repeated scheduler scans do not duplicate escalations or notifications."""
    now = datetime.now(timezone.utc)
    org_id = test_org.id
    task = Task(
        organization_id=org_id,
        assigned_to_id=test_user_owner.id,
        title="Idempotent Overdue Task",
        priority=TaskPriority.MEDIUM.value,
        status=TaskStatus.PENDING.value,
        due_date=now - timedelta(hours=36),
    )
    db_session.add(task)
    await db_session.commit()
    task_id = task.id

    # First run escalates the task
    res1 = await async_scan_and_escalate_overdue_tasks(session=db_session)
    assert res1["details"][org_id]["escalated_count"] == 1

    notifs_first = (await db_session.execute(
        select(Notification).where(
            Notification.organization_id == org_id,
            Notification.link == f"/tasks/{task_id}",
        )
    )).scalars().all()
    assert len(notifs_first) == 1

    # Second run finds no new tasks to escalate
    res2 = await async_scan_and_escalate_overdue_tasks(session=db_session)
    assert res2["details"][org_id]["escalated_count"] == 0

    notifs_second = (await db_session.execute(
        select(Notification).where(
            Notification.organization_id == org_id,
            Notification.link == f"/tasks/{task_id}",
        )
    )).scalars().all()
    assert len(notifs_second) == 1


@pytest.mark.asyncio
async def test_periodic_overdue_task_scheduler_failure_isolation_between_organizations(
    test_org: Organization,
    test_user_owner: User,
    db_session,
    monkeypatch,
):
    """Test that a mid-transaction failure in Organization A after database mutations have begun

    is properly rolled back, does not corrupt Org A's persisted state or leave orphan notifications,
    and does not prevent Organization B from being successfully processed and committed.
    """
    now = datetime.now(timezone.utc)
    org_a_id = str(test_org.id)

    # 1. Organization A: overdue task
    task_a = Task(
        organization_id=org_a_id,
        assigned_to_id=test_user_owner.id,
        title="Org A Faulty Run Task",
        priority=TaskPriority.MEDIUM.value,
        status=TaskStatus.PENDING.value,
        due_date=now - timedelta(hours=30),
    )
    db_session.add(task_a)

    # 2. Organization B: active organization with an assigned user and overdue task
    org_b = Organization(name="Healthy Org Beta", slug="healthy-org-beta", is_active=True)
    db_session.add(org_b)
    await db_session.flush()
    org_b_id = str(org_b.id)

    user_b = User(
        organization_id=org_b_id,
        email="owner@healthybeta.com",
        hashed_password="hashed_pw_test",
        first_name="Healthy",
        last_name="Owner",
        role="OWNER",
        is_active=True,
    )
    db_session.add(user_b)
    await db_session.flush()

    task_b = Task(
        organization_id=org_b_id,
        assigned_to_id=user_b.id,
        title="Org B Healthy Overdue Task",
        priority=TaskPriority.MEDIUM.value,
        status=TaskStatus.PENDING.value,
        due_date=now - timedelta(hours=30),
    )
    db_session.add(task_b)
    await db_session.commit()

    task_a_id = str(task_a.id)
    task_b_id = str(task_b.id)

    # Verify baseline state before scheduler execution
    assert task_a.priority == TaskPriority.MEDIUM.value
    assert task_a.extra_metadata is None or task_a.extra_metadata.get("escalated_at") is None
    assert task_b.priority == TaskPriority.MEDIUM.value
    assert task_b.extra_metadata is None or task_b.extra_metadata.get("escalated_at") is None

    # Intercept session commit to simulate failure AFTER Org A's escalation logic has
    # mutated task attributes and staged notification records in the active transaction
    real_commit = db_session.commit
    failure_triggered_for_org_a = False

    async def mock_commit_with_org_a_failure():
        nonlocal failure_triggered_for_org_a
        # Inspect whether Organization A's modifications are in the pending transaction
        has_org_a_changes = any(
            getattr(obj, "organization_id", None) == org_a_id
            for obj in list(db_session.dirty) + list(db_session.new)
        )
        if has_org_a_changes:
            failure_triggered_for_org_a = True
            # Verify that state modifications had indeed begun before the failure occurs
            assert task_a in db_session.dirty
            assert task_a.priority == TaskPriority.URGENT.value
            assert task_a.extra_metadata.get("escalated_at") is not None
            assert any(
                isinstance(obj, Notification) and obj.organization_id == org_a_id
                for obj in db_session.new
            )
            raise RuntimeError("Simulated mid-transaction database commit failure for Org A")
        return await real_commit()

    monkeypatch.setattr(db_session, "commit", mock_commit_with_org_a_failure)

    # Execute periodic scan and escalation
    res = await async_scan_and_escalate_overdue_tasks(session=db_session)

    # Verify that failure interceptor was executed after mutating Org A state
    assert failure_triggered_for_org_a is True

    # Verify scan results reflect isolated failure for Org A and success for Org B
    assert res["organizations_processed"] >= 2
    assert res["total_escalated"] == 1
    assert res["details"][org_a_id]["status"] == "failed"
    assert "Simulated mid-transaction database commit failure for Org A" in res["details"][org_a_id]["error"]
    assert res["details"][org_b_id]["status"] == "success"
    assert res["details"][org_b_id]["escalated_count"] == 1

    # Verify Org A in-session state was rolled back to its pre-escalation values
    await db_session.refresh(task_a)
    assert task_a.priority == TaskPriority.MEDIUM.value
    assert task_a.extra_metadata is None or task_a.extra_metadata.get("escalated_at") is None

    notifs_a = (await db_session.execute(
        select(Notification).where(Notification.organization_id == org_a_id)
    )).scalars().all()
    assert len(notifs_a) == 0

    # Verify Org B in-session state was escalated and persisted
    await db_session.refresh(task_b)
    assert task_b.priority == TaskPriority.URGENT.value
    assert task_b.extra_metadata is not None
    assert task_b.extra_metadata.get("escalated_at") is not None

    notifs_b = (await db_session.execute(
        select(Notification).where(Notification.organization_id == org_b_id)
    )).scalars().all()
    assert len(notifs_b) >= 1
    assert any(n.link == f"/tasks/{task_b_id}" for n in notifs_b)

    # Verify persisted database state using a clean, independent database session
    from tests.conftest import TestAsyncSessionLocal
    async with TestAsyncSessionLocal() as verify_session:
        db_task_a = await verify_session.get(Task, task_a_id)
        assert db_task_a is not None
        assert db_task_a.priority == TaskPriority.MEDIUM.value
        assert db_task_a.extra_metadata is None or db_task_a.extra_metadata.get("escalated_at") is None

        db_notifs_a = (await verify_session.execute(
            select(Notification).where(Notification.organization_id == org_a_id)
        )).scalars().all()
        assert len(db_notifs_a) == 0

        db_task_b = await verify_session.get(Task, task_b_id)
        assert db_task_b is not None
        assert db_task_b.priority == TaskPriority.URGENT.value
        assert db_task_b.extra_metadata is not None
        assert db_task_b.extra_metadata.get("escalated_at") is not None

        db_notifs_b = (await verify_session.execute(
            select(Notification).where(Notification.organization_id == org_b_id)
        )).scalars().all()
        assert len(db_notifs_b) >= 1
        assert any(n.link == f"/tasks/{task_b_id}" for n in db_notifs_b)
