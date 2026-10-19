from typing import Any, Dict, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import AsyncSessionLocal
from app.core.events import CRMEvent, event_dispatcher
from app.core.logging import logger
from app.workers.celery_app import celery_app, run_async_in_worker


async def async_dispatch_automation(
    organization_id: str,
    event_trigger: str,
    entity_type: str,
    entity_id: str,
    payload: Dict[str, Any],
    session: Optional[AsyncSession] = None,
) -> Dict[str, Any]:
    """Underlying async implementation of automation event dispatching."""
    async def _dispatch(db: AsyncSession):
        event = CRMEvent(
            event_name=event_trigger,
            organization_id=organization_id,
            entity_type=entity_type,
            entity_id=entity_id,
            payload=payload,
        )
        await event_dispatcher.dispatch(event, db)
        return {
            "organization_id": organization_id,
            "event_trigger": event_trigger,
            "status": "processed",
        }

    if session:
        return await _dispatch(session)
    else:
        async with AsyncSessionLocal() as db:
            return await _dispatch(db)


@celery_app.task(
    name="app.workers.automation_jobs.dispatch_event_automation",
    max_retries=3,
    autoretry_for=(Exception,),
    retry_backoff=True,
)
def dispatch_event_automation(
    organization_id: str,
    event_trigger: str,
    entity_type: str,
    entity_id: str,
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    """Background task to asynchronously evaluate and execute automation rules with isolated DB session."""
    logger.info(f"Background automation processing: {event_trigger} for org {organization_id}")
    return run_async_in_worker(
        async_dispatch_automation(
            organization_id, event_trigger, entity_type, entity_id, payload
        )
    )


async def async_scan_and_escalate_overdue_tasks(
    session: Optional[AsyncSession] = None,
) -> Dict[str, Any]:
    """Scan all active tenant organizations and escalate overdue tasks with isolated failure boundaries."""
    from sqlalchemy import select
    from app.modules.automation import workflows
    from app.modules.organizations.models import Organization

    async def _execute(db: AsyncSession) -> Dict[str, Any]:
        # Query active organizations strictly adhering to the Organization model schema
        stmt = select(Organization.id).where(Organization.is_active.is_(True))
        org_ids = (await db.execute(stmt)).scalars().all()

        results: Dict[str, Any] = {}
        total_escalated = 0

        for org_id in org_ids:
            try:
                escalated = await workflows.escalate_overdue_tasks(db, org_id)
                count = len(escalated)
                results[org_id] = {
                    "status": "success",
                    "escalated_count": count,
                }
                total_escalated += count
            except Exception as exc:
                await db.rollback()
                logger.error(
                    f"Error escalating overdue tasks for organization {org_id}: {exc}",
                    exc_info=True,
                )
                results[org_id] = {
                    "status": "failed",
                    "error": str(exc),
                }

        logger.info(
            f"Overdue task scan completed: {len(org_ids)} active orgs scanned, {total_escalated} tasks escalated."
        )
        return {
            "organizations_processed": len(org_ids),
            "total_escalated": total_escalated,
            "details": results,
        }

    if session:
        return await _execute(session)
    else:
        async with AsyncSessionLocal() as db:
            return await _execute(db)


@celery_app.task(
    name="app.workers.automation_jobs.scan_overdue_tasks_periodic",
    max_retries=3,
    autoretry_for=(Exception,),
    retry_backoff=True,
)
def scan_overdue_tasks_periodic() -> Dict[str, Any]:
    """Periodic Celery task scanning active organizations to escalate overdue tasks."""
    logger.info("Executing periodic overdue task escalation scan.")
    return run_async_in_worker(async_scan_and_escalate_overdue_tasks())


async def async_scan_overdue_deals(
    session: Optional[AsyncSession] = None,
) -> Dict[str, Any]:
    """Scan all active tenant organizations and process overdue deals with isolated failure boundaries."""
    from sqlalchemy import select
    from app.modules.automation import workflows
    from app.modules.organizations.models import Organization

    async def _execute(db: AsyncSession) -> Dict[str, Any]:
        stmt = select(Organization.id).where(Organization.is_active.is_(True))
        org_ids = (await db.execute(stmt)).scalars().all()

        results: Dict[str, Any] = {}
        total_processed = 0

        for org_id in org_ids:
            try:
                processed = await workflows.check_and_process_overdue_deals(db, org_id)
                count = len(processed)
                results[org_id] = {
                    "status": "success",
                    "processed_count": count,
                }
                total_processed += count
            except Exception as exc:
                await db.rollback()
                logger.error(
                    f"Error processing overdue deals for organization {org_id}: {exc}",
                    exc_info=True,
                )
                results[org_id] = {
                    "status": "failed",
                    "error": str(exc),
                }

        logger.info(
            f"Overdue deal scan completed: {len(org_ids)} active orgs scanned, {total_processed} deals processed."
        )
        return {
            "organizations_processed": len(org_ids),
            "total_processed": total_processed,
            "details": results,
        }

    if session:
        return await _execute(session)
    else:
        async with AsyncSessionLocal() as db:
            return await _execute(db)


@celery_app.task(
    name="app.workers.automation_jobs.scan_overdue_deals_periodic",
    max_retries=3,
    autoretry_for=(Exception,),
    retry_backoff=True,
)
def scan_overdue_deals_periodic() -> Dict[str, Any]:
    """Periodic Celery task scanning active organizations to process overdue deals."""
    logger.info("Executing periodic overdue deal processing scan.")
    return run_async_in_worker(async_scan_overdue_deals())
