"""Internal Application Event Dispatcher for NexusCRM.

Provides a lightweight, robust in-process event mechanism without requiring
heavyweight external message queues (like Kafka). Emits CRM domain events
with strict multi-tenant context (organization_id) and dispatches them
to registered workflow handlers.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine, Dict, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.logging import logger


# Standard CRM Event Names
class CRMEventType:
    LEAD_CREATED = "lead.created"
    LEAD_ASSIGNED = "lead.assigned"
    LEAD_CONVERTED = "lead.converted"
    ACTIVITY_CREATED = "activity.created"
    DEAL_CREATED = "deal.created"
    DEAL_STAGE_CHANGED = "deal.stage_changed"
    DEAL_WON = "deal.won"
    DEAL_LOST = "deal.lost"
    DEAL_OVERDUE = "deal.overdue"
    TASK_CREATED = "task.created"
    TASK_OVERDUE = "task.overdue"
    PROPOSAL_SENT = "proposal.sent"


@dataclass
class CRMEvent:
    event_name: str
    organization_id: str
    entity_type: str
    entity_id: str
    actor_id: Optional[str] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    payload: Dict[str, Any] = field(default_factory=dict)


EventHandler = Callable[[CRMEvent, AsyncSession], Coroutine[Any, Any, None]]


class EventDispatcher:
    def __init__(self):
        self._handlers: Dict[str, List[EventHandler]] = {}

    def subscribe(self, event_name: str, handler: EventHandler) -> None:
        """Register an async handler for a specific event name."""
        if event_name not in self._handlers:
            self._handlers[event_name] = []
        if handler not in self._handlers[event_name]:
            self._handlers[event_name].append(handler)
        logger.debug(f"Subscribed handler '{handler.__name__}' to event '{event_name}'")

    def register(self, event_name: str):
        """Decorator to register an async event handler."""
        def decorator(handler: EventHandler):
            self.subscribe(event_name, handler)
            return handler
        return decorator

    async def dispatch(self, event: CRMEvent, db: AsyncSession) -> None:
        """Dispatch a domain event to all registered handlers and dynamic rules.

        Isolates handler exceptions to prevent secondary workflow failures
        from crashing the primary transaction.
        """
        logger.info(
            f"Dispatching event '{event.event_name}' for org '{event.organization_id}' "
            f"on entity {event.entity_type}:{event.entity_id}"
        )

        # 1. Execute built-in programmatic workflow handlers
        handlers = self._handlers.get(event.event_name, [])
        for handler in handlers:
            try:
                await handler(event, db)
            except Exception as exc:
                logger.error(
                    f"Error in event handler '{handler.__name__}' for '{event.event_name}': {exc}",
                    exc_info=True,
                )

        # 2. Execute database-stored dynamic automation rules
        try:
            from app.modules.automation.service import AutomationService
            automation_svc = AutomationService(db, event.organization_id)
            await automation_svc.trigger_event(event.event_name, event.payload)
        except Exception as exc:
            logger.error(
                f"Error triggering dynamic automation rules for '{event.event_name}': {exc}",
                exc_info=True,
            )


# Global event dispatcher singleton
event_dispatcher = EventDispatcher()
