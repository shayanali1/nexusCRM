"""NexusCRM Operational Workflows and Automated Event Handlers.

Implements core domain workflows:
1. Lead Capture & Auto-Assignment (round-robin/least-assigned, 2h follow-up task, notification, AI brief)
2. Deal Won (customer status updates, 24h & 48h onboarding tasks, notification, activity logging)
3. Proposal Follow-Up (3-day follow-up task, idempotent)
4. Overdue Task Escalation (>24h overdue, priority to URGENT, notifications, idempotent)
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.events import CRMEvent, CRMEventType, event_dispatcher
from app.core.logging import logger
from app.modules.activities.models import Activity, ActivityType
from app.modules.companies.models import Company
from app.modules.contacts.models import Contact
from app.modules.deals.models import Deal, DealStatus
from app.modules.leads.models import Lead, LeadStatus
from app.modules.notifications.models import Notification
from app.modules.tasks.models import Task, TaskPriority, TaskStatus, TaskType
from app.modules.users.models import User


async def handle_lead_created(event: CRMEvent, db: AsyncSession) -> None:
    """Lead Capture & Auto-Assignment Workflow.

    1. If lead is unassigned, auto-assign via least-assigned algorithm across active org users.
    2. Idempotently create 'First Discovery Call' task due in 2 hours.
    3. Send notification to assigned sales rep.
    4. Enqueue/generate AI lead brief.
    """
    logger.info(f"Running Lead Capture Workflow for lead {event.entity_id} in org {event.organization_id}")
    stmt = (
        select(Lead)
        .where(Lead.id == event.entity_id, Lead.organization_id == event.organization_id)
        .options(selectinload(Lead.company))
    )
    result = await db.execute(stmt)
    lead = result.scalar_one_or_none()
    if not lead:
        logger.warning(f"Lead {event.entity_id} not found during workflow execution")
        return

    now = datetime.now(timezone.utc)

    # 1. Auto-assign if not assigned
    if not lead.assigned_to_id:
        users_stmt = (
            select(User)
            .where(User.organization_id == event.organization_id, User.is_active.is_(True))
        )
        active_users = (await db.execute(users_stmt)).scalars().all()
        if active_users:
            # Calculate open lead count per user (least-assigned algorithm)
            counts_stmt = (
                select(Lead.assigned_to_id, func.count(Lead.id).label("open_count"))
                .where(
                    Lead.organization_id == event.organization_id,
                    Lead.assigned_to_id.is_not(None),
                    Lead.status.notin_([LeadStatus.QUALIFIED.value, LeadStatus.LOST.value]),
                )
                .group_by(Lead.assigned_to_id)
            )
            counts_res = await db.execute(counts_stmt)
            user_counts = {row[0]: row[1] for row in counts_res.all()}

            # Pick user with lowest count
            selected_user = min(active_users, key=lambda u: user_counts.get(u.id, 0))
            lead.assigned_to_id = selected_user.id
            await db.flush()
            logger.info(f"Auto-assigned lead {lead.id} to user {selected_user.id} ({selected_user.full_name})")

    # 2. If assigned, create follow-up task and notify rep
    if lead.assigned_to_id:
        # Idempotency check for First Discovery Call task
        existing_task_stmt = select(Task).where(
            Task.organization_id == event.organization_id,
            Task.lead_id == lead.id,
            Task.title == "First Discovery Call",
        )
        existing_task = (await db.execute(existing_task_stmt)).scalars().first()
        if not existing_task:
            discovery_task = Task(
                organization_id=event.organization_id,
                lead_id=lead.id,
                assigned_to_id=lead.assigned_to_id,
                title="First Discovery Call",
                description=f"Conduct initial qualification and discovery call for {lead.title}.",
                task_type=TaskType.CALL.value,
                priority=TaskPriority.HIGH.value,
                status=TaskStatus.PENDING.value,
                due_date=now + timedelta(hours=2),
                extra_metadata={"automated": True, "workflow": "lead_capture"},
            )
            db.add(discovery_task)
            logger.info(f"Created 'First Discovery Call' task for lead {lead.id}")

        # Notification to assigned user
        notif = Notification(
            organization_id=event.organization_id,
            user_id=lead.assigned_to_id,
            title="New Lead Assigned",
            message=f"You have been assigned lead: '{lead.title}'. Discovery call is scheduled within 2 hours.",
            notification_type="LEAD_ASSIGNED",
            link=f"/leads/{lead.id}",
        )
        db.add(notif)

    # 3. Context preparation for background AI summary worker
    context = {
        "contact_name": lead.title,
        "company_name": lead.company.name if lead.company else None,
        "stage": lead.status or "New Lead",
        "estimated_value": float(lead.estimated_value or 0.0),
        "notes": lead.notes,
    }

    # 4. Commit database state so lead and workflow items are safely committed before dispatch
    await db.commit()

    # 5. Asynchronously dispatch AI Lead Brief generation to Celery worker task
    try:
        from app.workers.ai_jobs import process_async_lead_summary
        process_async_lead_summary.delay(
            event.organization_id,
            lead.id,
            context,
        )
        logger.info(
            f"Dispatched background AI summary task for lead {lead.id} in org {event.organization_id}"
        )
    except Exception as exc:
        logger.error(
            f"Failed to dispatch background AI summary task for lead {lead.id}: {exc}",
            exc_info=True,
        )


async def handle_deal_won(event: CRMEvent, db: AsyncSession) -> None:
    """Deal Won Workflow.

    1. Mark associated contact and company as active customers.
    2. Idempotently create 24h & 48h onboarding tasks.
    3. Notify managers and assigned sales rep.
    4. Record audit/activity timeline record.
    """
    logger.info(f"Running Deal Won Workflow for deal {event.entity_id} in org {event.organization_id}")
    stmt = select(Deal).where(Deal.id == event.entity_id, Deal.organization_id == event.organization_id)
    result = await db.execute(stmt)
    deal = result.scalar_one_or_none()
    if not deal:
        logger.warning(f"Deal {event.entity_id} not found during deal.won workflow")
        return

    now = datetime.now(timezone.utc)

    # 1. Update contact and company lifecycle stage to CUSTOMER
    if deal.contact_id:
        contact_stmt = select(Contact).where(
            Contact.id == deal.contact_id, Contact.organization_id == event.organization_id
        )
        contact = (await db.execute(contact_stmt)).scalar_one_or_none()
        if contact:
            fields = dict(contact.custom_fields or {})
            fields["lifecycle_stage"] = "CUSTOMER"
            fields["customer_since"] = now.isoformat()
            contact.custom_fields = fields

    if deal.company_id:
        company_stmt = select(Company).where(
            Company.id == deal.company_id, Company.organization_id == event.organization_id
        )
        company = (await db.execute(company_stmt)).scalar_one_or_none()
        if company:
            fields = dict(company.custom_fields or {})
            fields["lifecycle_stage"] = "CUSTOMER"
            fields["customer_since"] = now.isoformat()
            company.custom_fields = fields

    # 2. Idempotently create onboarding tasks
    # Task A: Kickoff Onboarding & Requirements Review (due in 24 hours)
    t1_title = "Kickoff Onboarding & Requirements Review"
    t1_stmt = select(Task).where(
        Task.organization_id == event.organization_id,
        Task.deal_id == deal.id,
        Task.title == t1_title,
    )
    if not (await db.execute(t1_stmt)).scalars().first():
        t1 = Task(
            organization_id=event.organization_id,
            deal_id=deal.id,
            contact_id=deal.contact_id,
            assigned_to_id=deal.assigned_to_id,
            title=t1_title,
            description=f"Host onboarding kickoff and technical requirements review for {deal.title}.",
            task_type=TaskType.MEETING.value,
            priority=TaskPriority.HIGH.value,
            status=TaskStatus.PENDING.value,
            due_date=now + timedelta(hours=24),
            extra_metadata={"automated": True, "workflow": "deal_won_onboarding"},
        )
        db.add(t1)

    # Task B: Send Customer Welcome Packet & Invoicing (due in 48 hours)
    t2_title = "Send Customer Welcome Packet & Invoicing"
    t2_stmt = select(Task).where(
        Task.organization_id == event.organization_id,
        Task.deal_id == deal.id,
        Task.title == t2_title,
    )
    if not (await db.execute(t2_stmt)).scalars().first():
        t2 = Task(
            organization_id=event.organization_id,
            deal_id=deal.id,
            contact_id=deal.contact_id,
            assigned_to_id=deal.assigned_to_id,
            title=t2_title,
            description="Send welcome pack, onboarding documentation, and accounting invoice instructions.",
            task_type=TaskType.OTHER.value,
            priority=TaskPriority.HIGH.value,
            status=TaskStatus.PENDING.value,
            due_date=now + timedelta(hours=48),
            extra_metadata={"automated": True, "workflow": "deal_won_onboarding"},
        )
        db.add(t2)

    # 3. Notification to assigned rep
    if deal.assigned_to_id:
        notif = Notification(
            organization_id=event.organization_id,
            user_id=deal.assigned_to_id,
            title="Deal Won!",
            message=f"Deal '{deal.title}' (${deal.value:,.2f}) closed successfully! Onboarding tasks created.",
            notification_type="DEAL_WON",
            link=f"/deals/{deal.id}",
        )
        db.add(notif)

    # 4. Activity entry for audit timeline
    act = Activity(
        organization_id=event.organization_id,
        deal_id=deal.id,
        contact_id=deal.contact_id,
        user_id=event.actor_id or deal.assigned_to_id,
        activity_type=ActivityType.STAGE_CHANGE.value,
        title=f"Deal Won: {deal.title}",
        description=f"Deal closed as WON with contract value {deal.value} {deal.currency}. Automated onboarding initialized.",
        performed_at=now,
        extra_metadata={"deal_id": deal.id, "value": deal.value, "currency": deal.currency},
    )
    db.add(act)

    await db.commit()


async def handle_deal_lost(event: CRMEvent, db: AsyncSession) -> None:
    """Deal Lost Workflow.

    1. Idempotently log an Activity timeline entry recording the deal loss and reason.
    2. Idempotently notify the assigned sales rep.
    """
    logger.info(f"Running Deal Lost Workflow for deal {event.entity_id} in org {event.organization_id}")
    stmt = select(Deal).where(Deal.id == event.entity_id, Deal.organization_id == event.organization_id)
    result = await db.execute(stmt)
    deal = result.scalar_one_or_none()
    if not deal:
        logger.warning(f"Deal {event.entity_id} not found during deal.lost workflow")
        return

    now = datetime.now(timezone.utc)

    # 1. Activity entry for audit timeline (Idempotency check: don't create duplicate activity)
    act_title = f"Deal Lost: {deal.title}"
    existing_act = (await db.execute(
        select(Activity).where(
            Activity.organization_id == event.organization_id,
            Activity.deal_id == deal.id,
            Activity.title == act_title,
        )
    )).scalars().first()

    if not existing_act:
        reason_text = f" Reason: {deal.lost_reason}" if deal.lost_reason else ""
        act = Activity(
            organization_id=event.organization_id,
            deal_id=deal.id,
            contact_id=deal.contact_id,
            user_id=event.actor_id or deal.assigned_to_id,
            activity_type=ActivityType.STAGE_CHANGE.value,
            title=act_title,
            description=f"Deal marked as LOST with contract value {deal.value} {deal.currency}.{reason_text}",
            performed_at=now,
            extra_metadata={
                "deal_id": deal.id,
                "value": deal.value,
                "currency": deal.currency,
                "lost_reason": deal.lost_reason,
            },
        )
        db.add(act)

    # 2. Notification to assigned rep
    if deal.assigned_to_id:
        notif_title = f"Deal Lost: {deal.title}"
        existing_notif = (await db.execute(
            select(Notification).where(
                Notification.organization_id == event.organization_id,
                Notification.user_id == deal.assigned_to_id,
                Notification.title == notif_title,
            )
        )).scalars().first()
        if not existing_notif:
            notif = Notification(
                organization_id=event.organization_id,
                user_id=deal.assigned_to_id,
                title=notif_title,
                message=f"Deal '{deal.title}' was marked as lost." + (f" Reason: {deal.lost_reason}" if deal.lost_reason else ""),
                notification_type="DEAL_LOST",
                link=f"/deals/{deal.id}",
            )
            db.add(notif)

    await db.commit()


async def handle_proposal_sent(event: CRMEvent, db: AsyncSession) -> None:
    """Proposal Follow-Up Workflow.

    Triggered when a proposal activity is recorded or deal moves to proposal stage.
    Idempotently creates a follow-up task due in 3 days (72 hours).
    """
    logger.info(f"Running Proposal Follow-Up Workflow for entity {event.entity_id} in org {event.organization_id}")
    deal_id: Optional[str] = None
    contact_id: Optional[str] = None
    assigned_to_id: Optional[str] = None
    title_suffix = "Proposal"

    now = datetime.now(timezone.utc)

    if event.entity_type == "deal":
        deal_id = event.entity_id
        deal = (
            await db.execute(
                select(Deal).where(Deal.id == deal_id, Deal.organization_id == event.organization_id)
            )
        ).scalar_one_or_none()
        if deal:
            contact_id = deal.contact_id
            assigned_to_id = deal.assigned_to_id
            title_suffix = deal.title
    elif event.entity_type == "activity":
        act = (
            await db.execute(
                select(Activity).where(Activity.id == event.entity_id, Activity.organization_id == event.organization_id)
            )
        ).scalar_one_or_none()
        if act:
            deal_id = act.deal_id
            contact_id = act.contact_id
            assigned_to_id = act.user_id
            if act.deal_id:
                deal = (
                    await db.execute(
                        select(Deal).where(Deal.id == act.deal_id, Deal.organization_id == event.organization_id)
                    )
                ).scalar_one_or_none()
                if deal:
                    title_suffix = deal.title
                    assigned_to_id = deal.assigned_to_id or assigned_to_id

    if not deal_id and not contact_id:
        return

    followup_title = f"Follow up on proposal: {title_suffix}"

    # Idempotency check: don't create duplicate proposal follow-up for this deal/contact
    stmt = select(Task).where(
        Task.organization_id == event.organization_id,
        Task.title == followup_title,
    )
    if deal_id:
        stmt = stmt.where(Task.deal_id == deal_id)
    elif contact_id:
        stmt = stmt.where(Task.contact_id == contact_id)

    existing = (await db.execute(stmt)).scalars().first()
    if not existing:
        task = Task(
            organization_id=event.organization_id,
            deal_id=deal_id,
            contact_id=contact_id,
            assigned_to_id=assigned_to_id,
            title=followup_title,
            description="Proposal sent. Follow up with the prospect regarding decision timeline and contract review.",
            task_type=TaskType.FOLLOW_UP.value,
            priority=TaskPriority.MEDIUM.value,
            status=TaskStatus.PENDING.value,
            due_date=now + timedelta(days=3),
            extra_metadata={"automated": True, "workflow": "proposal_followup"},
        )
        db.add(task)
        await db.commit()
        logger.info(f"Created proposal follow-up task '{followup_title}'")


async def escalate_overdue_tasks(db: AsyncSession, organization_id: str) -> List[Task]:
    """Scan and escalate tasks overdue by more than 24 hours.

    1. Elevates priority to URGENT.
    2. Marks task metadata with 'escalated_at' timestamp (idempotent guard).
    3. Notifies assigned user and managers.
    4. Dispatches task.overdue event.
    """
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=24)

    stmt = (
        select(Task)
        .where(
            Task.organization_id == organization_id,
            Task.due_date < cutoff,
            Task.status.in_([TaskStatus.PENDING.value, TaskStatus.IN_PROGRESS.value]),
        )
    )
    result = await db.execute(stmt)
    candidate_tasks = result.scalars().all()

    escalated: List[Task] = []
    for task in candidate_tasks:
        metadata = dict(task.extra_metadata or {})
        # Idempotency guard: do not re-escalate if already marked
        if metadata.get("escalated_at"):
            continue

        task.priority = TaskPriority.URGENT.value
        metadata["escalated_at"] = now.isoformat()
        metadata["escalation_reason"] = "Overdue by >24 hours"
        task.extra_metadata = metadata
        escalated.append(task)

        # Send notification to assigned user
        if task.assigned_to_id:
            notif = Notification(
                organization_id=organization_id,
                user_id=task.assigned_to_id,
                title="URGENT: Overdue Task Escalated",
                message=f"Task '{task.title}' is overdue by more than 24 hours. Priority has been escalated to URGENT.",
                notification_type="TASK_OVERDUE",
                link=f"/tasks/{task.id}",
            )
            db.add(notif)

        # Notify organization managers/admins
        mgr_stmt = (
            select(User)
            .where(
                User.organization_id == organization_id,
                User.is_active.is_(True),
                User.role.in_(["OWNER", "ADMIN", "MANAGER"]),
            )
        )
        managers = (await db.execute(mgr_stmt)).scalars().all()
        for mgr in managers:
            if mgr.id != task.assigned_to_id:
                db.add(
                    Notification(
                        organization_id=organization_id,
                        user_id=mgr.id,
                        title="Manager Alert: Escalated Task",
                        message=f"Task '{task.title}' is overdue by >24h and was escalated to URGENT.",
                        notification_type="TASK_OVERDUE",
                        link=f"/tasks/{task.id}",
                    )
                )

    if escalated:
        await db.commit()
        for t in escalated:
            await event_dispatcher.dispatch(
                CRMEvent(
                    event_name=CRMEventType.TASK_OVERDUE,
                    organization_id=organization_id,
                    entity_type="task",
                    entity_id=t.id,
                    payload={"task_id": t.id, "title": t.title, "due_date": t.due_date.isoformat()},
                ),
                db,
            )

    logger.info(f"Escalated {len(escalated)} overdue tasks in org {organization_id}")
    return escalated


async def check_and_process_overdue_deals(db: AsyncSession, organization_id: str) -> List[Deal]:
    """Scan and process open deals whose expected close date has passed.

    1. Idempotently creates a follow-up task 'Review Overdue Deal: <title>' for assigned owner.
    2. Sends notification to assigned owner.
    3. Dispatches deal.overdue CRM event.
    """
    now = datetime.now(timezone.utc)
    stmt = (
        select(Deal)
        .where(
            Deal.organization_id == organization_id,
            Deal.status == DealStatus.OPEN.value,
            Deal.expected_close_date.is_not(None),
            Deal.expected_close_date < now,
        )
        .limit(200)
    )
    result = await db.execute(stmt)
    overdue_deals = result.scalars().all()

    processed_deals: List[Deal] = []
    for deal in overdue_deals:
        followup_title = f"Review Overdue Deal: {deal.title}"

        # Idempotency check: do not create duplicate task if an open task already exists
        existing_task = (await db.execute(
            select(Task).where(
                Task.organization_id == organization_id,
                Task.deal_id == deal.id,
                Task.title == followup_title,
                Task.status.in_([TaskStatus.PENDING.value, TaskStatus.IN_PROGRESS.value]),
            )
        )).scalars().first()

        if not existing_task:
            task = Task(
                organization_id=organization_id,
                deal_id=deal.id,
                contact_id=deal.contact_id,
                assigned_to_id=deal.assigned_to_id,
                title=followup_title,
                description=(
                    f"Deal '{deal.title}' passed its expected close date "
                    f"({deal.expected_close_date.strftime('%Y-%m-%d')}). "
                    f"Review pipeline status and update expected close date or stage outcome."
                ),
                task_type=TaskType.FOLLOW_UP.value,
                priority=TaskPriority.HIGH.value,
                status=TaskStatus.PENDING.value,
                due_date=now + timedelta(hours=24),
                extra_metadata={"automated": True, "workflow": "deal_overdue"},
            )
            db.add(task)
            processed_deals.append(deal)

            # Notification to assigned user
            if deal.assigned_to_id:
                notif = Notification(
                    organization_id=organization_id,
                    user_id=deal.assigned_to_id,
                    title="Deal Overdue Alert",
                    message=f"Deal '{deal.title}' has passed its expected close date. A review task has been assigned.",
                    notification_type="DEAL_OVERDUE",
                    link=f"/deals/{deal.id}",
                )
                db.add(notif)

    if processed_deals:
        await db.commit()
        for d in processed_deals:
            await event_dispatcher.dispatch(
                CRMEvent(
                    event_name=CRMEventType.DEAL_OVERDUE,
                    organization_id=organization_id,
                    entity_type="deal",
                    entity_id=d.id,
                    payload={
                        "deal_id": d.id,
                        "title": d.title,
                        "value": d.value,
                        "expected_close_date": d.expected_close_date.isoformat() if d.expected_close_date else None,
                        "assigned_to_id": d.assigned_to_id,
                        "stage_id": d.stage_id,
                        "pipeline_id": d.pipeline_id,
                    },
                ),
                db,
            )

    logger.info(f"Processed {len(processed_deals)} overdue deals in org {organization_id}")
    return processed_deals


def register_standard_workflows():
    """Register built-in CRM operational workflows with the global event dispatcher."""
    event_dispatcher.subscribe(CRMEventType.LEAD_CREATED, handle_lead_created)
    event_dispatcher.subscribe(CRMEventType.DEAL_WON, handle_deal_won)
    event_dispatcher.subscribe(CRMEventType.DEAL_LOST, handle_deal_lost)
    event_dispatcher.subscribe(CRMEventType.PROPOSAL_SENT, handle_proposal_sent)
    logger.info("NexusCRM standard operational workflows successfully registered.")


# Automatically register on import
register_standard_workflows()
