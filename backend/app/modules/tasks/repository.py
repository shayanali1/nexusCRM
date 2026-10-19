from datetime import datetime, timezone
from typing import Dict, List, Optional
from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import BadRequestException, NotFoundException
from app.modules.contacts.models import Contact
from app.modules.deals.models import Deal
from app.modules.leads.models import Lead
from app.modules.tasks.models import Task, TaskPriority, TaskStatus
from app.modules.tasks.schemas import TaskCreate, TaskSummaryMetrics, TaskUpdate
from app.modules.users.models import User

TASKS_SORT_FIELDS: Dict[str, any] = {
    "due_date": Task.due_date,
    "priority": Task.priority,
    "status": Task.status,
    "created_at": Task.created_at,
    "title": Task.title,
}


class TaskRepository:
    def __init__(self, db: AsyncSession, organization_id: str):
        self.db = db
        self.org_id = organization_id

    async def _validate_relationships(
        self,
        lead_id: Optional[str] = None,
        contact_id: Optional[str] = None,
        deal_id: Optional[str] = None,
        assigned_to_id: Optional[str] = None,
    ) -> None:
        """Verify referenced entities belong to the same tenant organization and exist."""
        if lead_id and lead_id.strip():
            lead_stmt = select(Lead.id).where(
                Lead.id == lead_id.strip(),
                Lead.organization_id == self.org_id,
            )
            if not (await self.db.execute(lead_stmt)).scalar_one_or_none():
                raise NotFoundException("Lead not found.")

        if contact_id and contact_id.strip():
            ct_stmt = select(Contact.id).where(
                Contact.id == contact_id.strip(),
                Contact.organization_id == self.org_id,
            )
            if not (await self.db.execute(ct_stmt)).scalar_one_or_none():
                raise NotFoundException("Contact not found.")

        if deal_id and deal_id.strip():
            d_stmt = select(Deal.id).where(
                Deal.id == deal_id.strip(),
                Deal.organization_id == self.org_id,
            )
            if not (await self.db.execute(d_stmt)).scalar_one_or_none():
                raise NotFoundException("Deal not found.")

        if assigned_to_id and assigned_to_id.strip():
            u_stmt = select(User.id).where(
                User.id == assigned_to_id.strip(),
                User.organization_id == self.org_id,
                User.is_active.is_(True),
            )
            if not (await self.db.execute(u_stmt)).scalar_one_or_none():
                raise NotFoundException("User not found.")

    async def list_all(
        self,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        assigned_to_id: Optional[str] = None,
        lead_id: Optional[str] = None,
        contact_id: Optional[str] = None,
        deal_id: Optional[str] = None,
        filter_type: Optional[str] = None,  # "overdue", "today", "upcoming"
        search: Optional[str] = None,
        sort_by: Optional[str] = None,
        sort_order: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Task]:
        if start_date and end_date and start_date > end_date:
            raise BadRequestException("Start date cannot be after end date.")

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
        )

        if status and status.strip():
            clean_status = status.strip().upper()
            stmt = stmt.where(Task.status == clean_status)
        if priority and priority.strip():
            clean_priority = priority.strip().upper()
            stmt = stmt.where(Task.priority == clean_priority)
        if assigned_to_id and assigned_to_id.strip():
            stmt = stmt.where(Task.assigned_to_id == assigned_to_id.strip())
        if lead_id and lead_id.strip():
            stmt = stmt.where(Task.lead_id == lead_id.strip())
        if contact_id and contact_id.strip():
            stmt = stmt.where(Task.contact_id == contact_id.strip())
        if deal_id and deal_id.strip():
            stmt = stmt.where(Task.deal_id == deal_id.strip())

        # High-signal follow-up filters
        if filter_type and filter_type.strip():
            clean_filter_type = filter_type.strip().lower()
            if clean_filter_type == "overdue":
                stmt = stmt.where(
                    Task.due_date < now,
                    Task.status.in_([TaskStatus.PENDING.value, TaskStatus.IN_PROGRESS.value]),
                )
            elif clean_filter_type == "today":
                start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
                end_of_day = now.replace(hour=23, minute=59, second=59, microsecond=999999)
                stmt = stmt.where(
                    Task.due_date >= start_of_day,
                    Task.due_date <= end_of_day,
                    Task.status != TaskStatus.COMPLETED.value,
                )
            elif clean_filter_type == "upcoming":
                stmt = stmt.where(
                    Task.due_date > now,
                    Task.status != TaskStatus.COMPLETED.value,
                )
            else:
                raise BadRequestException("Invalid filter_type. Must be one of: overdue, today, upcoming.")

        # Search across title and description
        if search and search.strip():
            search_pattern = f"%{search.strip()}%"
            stmt = stmt.where(or_(Task.title.ilike(search_pattern), Task.description.ilike(search_pattern)))

        # Date range filters on due_date
        if start_date:
            stmt = stmt.where(Task.due_date >= start_date)
        if end_date:
            stmt = stmt.where(Task.due_date <= end_date)

        # Dynamic Sorting
        clean_sort_by = sort_by.strip().lower() if sort_by and sort_by.strip() else None
        clean_sort_order = sort_order.strip().lower() if sort_order and sort_order.strip() else None

        if clean_sort_order is not None and clean_sort_order not in ("asc", "desc"):
            raise BadRequestException("Invalid sort order. Must be 'asc' or 'desc'.")

        if clean_sort_by is not None:
            if clean_sort_by not in TASKS_SORT_FIELDS:
                allowed = ", ".join(sorted(TASKS_SORT_FIELDS.keys()))
                raise BadRequestException(f"Invalid sort field '{clean_sort_by}'. Allowed fields: {allowed}")

            direction = clean_sort_order if clean_sort_order else "asc"
            col = TASKS_SORT_FIELDS[clean_sort_by]
            stmt = stmt.order_by(col.desc() if direction == "desc" else col.asc(), Task.id.asc())
        elif clean_sort_order is not None:
            direction = clean_sort_order
            stmt = stmt.order_by(Task.due_date.desc() if direction == "desc" else Task.due_date.asc(), Task.id.asc())
        else:
            # Default sorting: due_date.asc(), secondary Task.id.asc()
            stmt = stmt.order_by(Task.due_date.asc(), Task.id.asc())

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
        assigned_to_id = data.assigned_to_id or created_by_id
        await self._validate_relationships(
            lead_id=data.lead_id,
            contact_id=data.contact_id,
            deal_id=data.deal_id,
            assigned_to_id=assigned_to_id,
        )
        task = Task(
            organization_id=self.org_id,
            created_by_id=created_by_id,
            assigned_to_id=assigned_to_id,
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
        update_dict = data.model_dump(exclude_unset=True)

        if any(k in update_dict for k in ("lead_id", "contact_id", "deal_id", "assigned_to_id")):
            await self._validate_relationships(
                lead_id=update_dict.get("lead_id"),
                contact_id=update_dict.get("contact_id"),
                deal_id=update_dict.get("deal_id"),
                assigned_to_id=update_dict.get("assigned_to_id"),
            )

        for field, value in update_dict.items():
            if hasattr(value, "value"):
                value = value.value
            if field == "status" and value == TaskStatus.COMPLETED.value and not task.completed_at:
                task.completed_at = datetime.now(timezone.utc)
            setattr(task, field, value)
        await self.db.commit()
        await self.db.refresh(task)
        return task

    async def get_metrics(self, assigned_to_id: Optional[str] = None) -> TaskSummaryMetrics:
        now = datetime.now(timezone.utc)
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = now.replace(hour=23, minute=59, second=59, microsecond=999999)

        stmt = select(
            func.count(Task.id).label("total"),
            func.count(
                case(
                    (
                        (Task.due_date < now) & Task.status.in_([TaskStatus.PENDING.value, TaskStatus.IN_PROGRESS.value]),
                        Task.id,
                    ),
                    else_=None,
                )
            ).label("overdue"),
            func.count(
                case(
                    (
                        (Task.due_date >= start_of_day) & (Task.due_date <= end_of_day) & (Task.status != TaskStatus.COMPLETED.value),
                        Task.id,
                    ),
                    else_=None,
                )
            ).label("due_today"),
            func.count(
                case(
                    (
                        (Task.due_date > now) & (Task.status != TaskStatus.COMPLETED.value),
                        Task.id,
                    ),
                    else_=None,
                )
            ).label("upcoming"),
            func.count(
                case(
                    (
                        Task.status == TaskStatus.COMPLETED.value,
                        Task.id,
                    ),
                    else_=None,
                )
            ).label("completed"),
        ).where(Task.organization_id == self.org_id)

        if assigned_to_id and assigned_to_id.strip():
            stmt = stmt.where(Task.assigned_to_id == assigned_to_id.strip())

        row = (await self.db.execute(stmt)).one()
        return TaskSummaryMetrics(
            total_tasks=row.total or 0,
            overdue_count=row.overdue or 0,
            due_today_count=row.due_today or 0,
            upcoming_count=row.upcoming or 0,
            completed_count=row.completed or 0,
        )

    async def delete(self, task: Task) -> None:
        await self.db.delete(task)
        await self.db.commit()
