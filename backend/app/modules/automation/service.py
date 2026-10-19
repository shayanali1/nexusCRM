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

    async def delete_rule(self, rule_id: str) -> None:
        rule = await self.get_rule(rule_id)
        if not rule:
            raise NotFoundException("Automation rule not found.")
        await self.db.delete(rule)
        await self.db.commit()

    @staticmethod
    def _evaluate_conditions(conditions: List[Dict[str, Any]], payload: Dict[str, Any]) -> bool:
        """Evaluate if an event payload satisfies all rule conditions."""
        if not conditions:
            return True
        for cond in conditions:
            field = cond.get("field")
            op = (cond.get("operator") or "equals").lower()
            expected = cond.get("value")
            actual = payload.get(field)

            if op in ("equals", "eq", "=="):
                if isinstance(actual, str) and isinstance(expected, str):
                    if actual.strip().lower() != expected.strip().lower():
                        return False
                elif actual != expected:
                    return False
            elif op in ("not_equals", "ne", "!="):
                if isinstance(actual, str) and isinstance(expected, str):
                    if actual.strip().lower() == expected.strip().lower():
                        return False
                elif actual == expected:
                    return False
            elif op in ("in", "contains"):
                if isinstance(expected, list):
                    if actual not in expected:
                        return False
                elif isinstance(actual, (list, str)) and isinstance(expected, str):
                    if expected.lower() not in str(actual).lower():
                        return False
                else:
                    return False
            elif op in ("greater_than", "gt", ">"):
                if actual is None or actual <= expected:
                    return False
            elif op in ("less_than", "lt", "<"):
                if actual is None or actual >= expected:
                    return False
        return True

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
            if not self._evaluate_conditions(rule.conditions, payload):
                continue
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
            # 1. Tenant validation for entity references
            deal_id = payload.get("deal_id") or config.get("deal_id")
            contact_id = payload.get("contact_id") or config.get("contact_id")
            lead_id = payload.get("lead_id") or config.get("lead_id")
            assigned_to_id = config.get("assigned_to_id") or payload.get("assigned_to_id")

            # Validate deal_id belongs to this org
            if deal_id:
                from app.modules.deals.models import Deal
                deal_chk = (await self.db.execute(
                    select(Deal.id).where(Deal.id == deal_id, Deal.organization_id == self.org_id)
                )).scalar_one_or_none()
                if not deal_chk:
                    logger.warning(f"Automation create_task rejected invalid or foreign deal_id: {deal_id}")
                    return

            # Validate contact_id belongs to this org
            if contact_id:
                from app.modules.contacts.models import Contact
                contact_chk = (await self.db.execute(
                    select(Contact.id).where(Contact.id == contact_id, Contact.organization_id == self.org_id)
                )).scalar_one_or_none()
                if not contact_chk:
                    logger.warning(f"Automation create_task rejected invalid or foreign contact_id: {contact_id}")
                    return

            # Validate lead_id belongs to this org
            if lead_id:
                from app.modules.leads.models import Lead
                lead_chk = (await self.db.execute(
                    select(Lead.id).where(Lead.id == lead_id, Lead.organization_id == self.org_id)
                )).scalar_one_or_none()
                if not lead_chk:
                    logger.warning(f"Automation create_task rejected invalid or foreign lead_id: {lead_id}")
                    return

            # Validate assigned_to_id belongs to this org and is active
            if assigned_to_id:
                from app.modules.users.models import User
                user_chk = (await self.db.execute(
                    select(User.id).where(
                        User.id == assigned_to_id,
                        User.organization_id == self.org_id,
                        User.is_active.is_(True),
                    )
                )).scalar_one_or_none()
                if not user_chk:
                    logger.warning(f"Automation create_task invalid or inactive assignee {assigned_to_id}; clearing")
                    assigned_to_id = None

            due_hours = config.get("due_in_hours", 24)
            task_title = config.get("title", f"Follow up: {payload.get('title', 'Deal')}")

            # 2. Duplicate prevention / idempotency check
            dup_stmt = select(Task).where(
                Task.organization_id == self.org_id,
                Task.title == task_title,
                Task.status.in_([TaskStatus.PENDING.value, TaskStatus.IN_PROGRESS.value]),
            )
            if deal_id:
                dup_stmt = dup_stmt.where(Task.deal_id == deal_id)
            elif lead_id:
                dup_stmt = dup_stmt.where(Task.lead_id == lead_id)
            elif contact_id:
                dup_stmt = dup_stmt.where(Task.contact_id == contact_id)

            existing_task = (await self.db.execute(dup_stmt)).scalars().first()
            if existing_task:
                logger.info(f"Duplicate task '{task_title}' prevented for entity in org {self.org_id}")
                return

            task = Task(
                organization_id=self.org_id,
                title=task_title,
                description=config.get("description", "Automated follow-up task triggered by system workflow."),
                priority=config.get("priority", TaskPriority.HIGH.value),
                status=TaskStatus.PENDING.value,
                due_date=now + timedelta(hours=due_hours),
                lead_id=lead_id,
                contact_id=contact_id,
                deal_id=deal_id,
                assigned_to_id=assigned_to_id,
                extra_metadata={"automated": True, "source": "automation_rule"},
            )
            self.db.add(task)
            await self.db.commit()

        elif action_type == "send_notification":
            user_id = config.get("user_id") or payload.get("assigned_to_id")
            if user_id:
                from app.modules.users.models import User
                user_chk = (await self.db.execute(
                    select(User.id).where(
                        User.id == user_id,
                        User.organization_id == self.org_id,
                        User.is_active.is_(True),
                    )
                )).scalar_one_or_none()
                if not user_chk:
                    return

                notif_title = config.get("title", "CRM Automation Alert")
                # Idempotency check for notification within same day
                dup_notif = select(Notification).where(
                    Notification.organization_id == self.org_id,
                    Notification.user_id == user_id,
                    Notification.title == notif_title,
                    Notification.created_at >= now - timedelta(hours=1),
                )
                if (await self.db.execute(dup_notif)).scalars().first():
                    return

                notif = Notification(
                    organization_id=self.org_id,
                    user_id=user_id,
                    title=notif_title,
                    message=config.get("message", f"Event {payload.get('event', 'update')} occurred."),
                    notification_type="AUTOMATION",
                    link=payload.get("link"),
                )
                self.db.add(notif)
                await self.db.commit()

        elif action_type == "create_activity":
            from app.modules.activities.models import Activity, ActivityType
            deal_id = payload.get("deal_id") or config.get("deal_id")
            contact_id = payload.get("contact_id") or config.get("contact_id")
            user_id = config.get("user_id") or payload.get("assigned_to_id")
            act_title = config.get("title", f"Automation Note: {payload.get('title', 'Deal')}")

            # Idempotency check for activity
            dup_act = select(Activity).where(
                Activity.organization_id == self.org_id,
                Activity.title == act_title,
            )
            if deal_id:
                dup_act = dup_act.where(Activity.deal_id == deal_id)
            if (await self.db.execute(dup_act)).scalars().first():
                return

            act = Activity(
                organization_id=self.org_id,
                deal_id=deal_id,
                contact_id=contact_id,
                user_id=user_id,
                activity_type=config.get("activity_type", ActivityType.NOTE.value),
                title=act_title,
                description=config.get("description", "Automated activity logged by system workflow."),
                performed_at=now,
                extra_metadata={"automated": True, "source": "automation_rule"},
            )
            self.db.add(act)
            await self.db.commit()

        elif action_type == "assign_user":
            new_assignee_id = config.get("assigned_to_id")
            deal_id = payload.get("deal_id")
            if deal_id and new_assignee_id:
                from app.modules.deals.models import Deal
                from app.modules.users.models import User
                user_chk = (await self.db.execute(
                    select(User.id).where(
                        User.id == new_assignee_id,
                        User.organization_id == self.org_id,
                        User.is_active.is_(True),
                    )
                )).scalar_one_or_none()
                if user_chk:
                    deal = (await self.db.execute(
                        select(Deal).where(Deal.id == deal_id, Deal.organization_id == self.org_id)
                    )).scalar_one_or_none()
                    if deal:
                        deal.assigned_to_id = new_assignee_id
                        await self.db.commit()
