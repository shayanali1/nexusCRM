from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.core.exceptions import NotFoundException
from app.core.logging import logger
from app.modules.automation.models import AutomationAction, AutomationRule
from app.modules.automation.schemas import AutomationRuleCreate, AutomationRuleUpdate
from app.modules.notifications.models import Notification
from app.modules.tasks.models import Task, TaskPriority, TaskStatus


class AutomationService:
    def __init__(self, db: AsyncSession, organization_id: str):
        self.db = db
        self.org_id = organization_id

    async def list_rules(self) -> List[AutomationRule]:
        stmt = (
            select(AutomationRule)
            .where(AutomationRule.organization_id == self.org_id)
            .options(selectinload(AutomationRule.actions))
            .order_by(AutomationRule.created_at.desc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_rule(self, rule_id: str) -> Optional[AutomationRule]:
        stmt = (
            select(AutomationRule)
            .where(AutomationRule.id == rule_id, AutomationRule.organization_id == self.org_id)
            .options(selectinload(AutomationRule.actions))
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def create_rule(self, data: AutomationRuleCreate) -> AutomationRule:
        rule = AutomationRule(
            organization_id=self.org_id,
            name=data.name,
            description=data.description,
            event_trigger=data.event_trigger,
            conditions=data.conditions,
            is_active=data.is_active,
        )
        self.db.add(rule)
        await self.db.flush()

        for idx, act in enumerate(data.actions):
            action = AutomationAction(
                rule_id=rule.id,
                action_type=act.action_type,
                action_config=act.action_config,
                execution_order=act.execution_order or (idx + 1),
            )
            self.db.add(action)

        await self.db.commit()
        return await self.get_rule(rule.id) or rule

    async def update_rule(self, rule_id: str, data: AutomationRuleUpdate) -> AutomationRule:
        rule = await self.get_rule(rule_id)
        if not rule:
            raise NotFoundException("Automation rule not found.")
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(rule, field, value)
        await self.db.commit()
        return await self.get_rule(rule.id) or rule

    async def trigger_event(self, event_name: str, payload: Dict[str, Any]) -> List[str]:
        """Evaluate and execute automation rules matching an event."""
        stmt = (
            select(AutomationRule)
            .where(
                AutomationRule.organization_id == self.org_id,
                AutomationRule.event_trigger == event_name,
                AutomationRule.is_active.is_(True),
            )
            .options(selectinload(AutomationRule.actions))
        )
        result = await self.db.execute(stmt)
        rules = result.scalars().all()

        executed_actions: List[str] = []
        for rule in rules:
            for action in rule.actions:
                try:
                    await self._execute_action(action.action_type, action.action_config, payload)
                    executed_actions.append(f"Rule '{rule.name}': {action.action_type}")
                except Exception as exc:
                    logger.error(f"Failed to execute action {action.action_type} for rule {rule.id}: {exc}")

        return executed_actions

    async def _execute_action(self, action_type: str, config: Dict[str, Any], payload: Dict[str, Any]) -> None:
        now = datetime.now(timezone.utc)
        if action_type == "create_task":
            due_hours = config.get("due_in_hours", 24)
            task = Task(
                organization_id=self.org_id,
                title=config.get("title", f"Follow up: {payload.get('title', 'Lead')}"),
                description=config.get("description", "Automated follow-up task triggered by system workflow."),
                priority=config.get("priority", TaskPriority.HIGH.value),
                status=TaskStatus.PENDING.value,
                due_date=now + timedelta(hours=due_hours),
                lead_id=payload.get("lead_id"),
                contact_id=payload.get("contact_id"),
                deal_id=payload.get("deal_id"),
                assigned_to_id=config.get("assigned_to_id") or payload.get("assigned_to_id"),
            )
            self.db.add(task)
            await self.db.commit()
        elif action_type == "send_notification":
            user_id = config.get("user_id") or payload.get("assigned_to_id")
            if user_id:
                notif = Notification(
                    organization_id=self.org_id,
                    user_id=user_id,
                    title=config.get("title", "CRM Automation Alert"),
                    message=config.get("message", f"Event {payload.get('event', 'update')} occurred."),
                    notification_type="AUTOMATION",
                    link=payload.get("link"),
                )
                self.db.add(notif)
                await self.db.commit()
