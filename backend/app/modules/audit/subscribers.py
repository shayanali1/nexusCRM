from typing import Any, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.events import CRMEvent, CRMEventType, event_dispatcher
from app.core.logging import logger
from app.modules.audit.repository import AuditLogRepository


async def handle_audit_event(event: CRMEvent, db: AsyncSession) -> None:
    """Event subscriber that automatically writes an immutable AuditLog entry upon CRM domain events."""
    if not event.organization_id or not db:
        return

    try:
        # Determine actor / user_id
        candidate_user_id = event.actor_id
        if not candidate_user_id and isinstance(event.payload, dict):
            candidate_user_id = event.payload.get("user_id") or event.payload.get("actor_id")

        payload = event.payload if isinstance(event.payload, dict) else {}
        ip_address = payload.get("ip_address") if isinstance(payload, dict) else None
        user_agent = payload.get("user_agent") if isinstance(payload, dict) else None

        repo = AuditLogRepository(db, event.organization_id)
        await repo.create_log(
            action=event.event_name,
            entity_type=event.entity_type,
            entity_id=event.entity_id,
            user_id=candidate_user_id,
            changes=payload,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        logger.debug(
            f"Audit log recorded for '{event.event_name}' on {event.entity_type}:{event.entity_id} "
            f"in org '{event.organization_id}'"
        )
    except Exception as exc:
        logger.error(
            f"Failed to record audit log for event '{event.event_name}' in org '{event.organization_id}': {exc}",
            exc_info=True,
        )


def register_audit_subscribers() -> None:
    """Register the audit log event handler across all defined CRMEventType events."""
    event_names = [
        val for key, val in vars(CRMEventType).items()
        if isinstance(val, str) and not key.startswith("_")
    ]
    for evt in event_names:
        event_dispatcher.subscribe(evt, handle_audit_event)
    logger.info(f"Registered audit logging subscribers for {len(event_names)} CRM domain event types.")


# Automatically register on import
register_audit_subscribers()
