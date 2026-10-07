from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.modules.tasks.models import Task, TaskPriority, TaskStatus
from app.modules.tasks.schemas import TaskCreate, TaskSummaryMetrics, TaskUpdate


class TaskRepository:
    def __init__(self, db: AsyncSession, organization_id: str):
        self.db = db
        self.org_id = organization_id

    async def list_all(
        self,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        assigned_to_id: Optional[str] = None,
        lead_id: Optional[str] = None,
        contact_id: Optional[str] = None,
        deal_id: Optional[str] = None,
        filter_type: Optional[str] = None,  # "overdue", "today", "upcoming"
        limit: int = 100,
        offset: int = 0,
    ) -> List[Task]:
        now = datetime.now(timezone.utc)
        stmt = (
            select(Task)
            .where(Task.organization_id == self.org_id)
            .options(
                selectinload(Task.assigned_to),
                selectinload(Task.lead),
                selectinload(Task.contact),
                selectinload(Task.deal),
            )
            .order_by(Task.due_date.asc())
        )

        if status:
            stmt = stmt.where(Task.status == status.upper())
        if priority:
            stmt = stmt.where(Task.priority == priority.upper())
        if assigned_to_id:
            stmt = stmt.where(Task.assigned_to_id == assigned_to_id)
        if lead_id:
            stmt = stmt.where(Task.lead_id == lead_id)
        if contact_id:
            stmt = stmt.where(Task.contact_id == contact_id)
        if deal_id:
            stmt = stmt.where(Task.deal_id == deal_id)

        # High-signal follow-up filters
        if filter_type == "overdue":
            stmt = stmt.where(
                Task.due_date < now,
                Task.status.in_([TaskStatus.PENDING.value, TaskStatus.IN_PROGRESS.value]),
            )
        elif filter_type == "today":
            start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end_of_day = now.replace(hour=23, minute=59, second=59, microsecond=999999)
            stmt = stmt.where(
                Task.due_date >= start_of_day,
                Task.due_date <= end_of_day,
                Task.status != TaskStatus.COMPLETED.value,
            )
        elif filter_type == "upcoming":
            stmt = stmt.where(
                Task.due_date > now,
                Task.status != TaskStatus.COMPLETED.value,
            )

        stmt = stmt.offset(offset).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id(self, task_id: str) -> Optional[Task]:
        stmt = (
            select(Task)
            .where(Task.id == task_id, Task.organization_id == self.org_id)
            .options(
                selectinload(Task.assigned_to),
                selectinload(Task.lead),
                selectinload(Task.contact),
                selectinload(Task.deal),
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, data: TaskCreate, created_by_id: Optional[str] = None) -> Task:
        task = Task(
            organization_id=self.org_id,
            created_by_id=created_by_id,
            assigned_to_id=data.assigned_to_id or created_by_id,
            lead_id=data.lead_id,
            contact_id=data.contact_id,
            deal_id=data.deal_id,
            title=data.title,
            description=data.description,
            task_type=data.task_type.value if hasattr(data.task_type, "value") else str(data.task_type),
            priority=data.priority.value if hasattr(data.priority, "value") else str(data.priority),
            status=data.status.value if hasattr(data.status, "value") else str(data.status),
            due_date=data.due_date,
        )
        self.db.add(task)
        await self.db.commit()
        await self.db.refresh(task)
        return task

    async def update(self, task: Task, data: TaskUpdate) -> Task:
        for field, value in data.model_dump(exclude_unset=True).items():
            if hasattr(value, "value"):
                value = value.value
            if field == "status" and value == TaskStatus.COMPLETED.value and not task.completed_at:
                task.completed_at = datetime.now(timezone.utc)
            setattr(task, field, value)
        await self.db.commit()
        await self.db.refresh(task)
        return task

    async def get_metrics(self) -> TaskSummaryMetrics:
        now = datetime.now(timezone.utc)
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = now.replace(hour=23, minute=59, second=59, microsecond=999999)

        all_tasks = await self.list_all(limit=1000)
        total = len(all_tasks)
        overdue = sum(1 for t in all_tasks if t.due_date < now and t.status in ["PENDING", "IN_PROGRESS"])
        due_today = sum(1 for t in all_tasks if start_of_day <= t.due_date <= end_of_day and t.status != "COMPLETED")
        upcoming = sum(1 for t in all_tasks if t.due_date > now and t.status != "COMPLETED")
        completed = sum(1 for t in all_tasks if t.status == "COMPLETED")

        return TaskSummaryMetrics(
            total_tasks=total,
            overdue_count=overdue,
            due_today_count=due_today,
            upcoming_count=upcoming,
            completed_count=completed,
        )

    async def delete(self, task: Task) -> None:
        await self.db.delete(task)
        await self.db.commit()
