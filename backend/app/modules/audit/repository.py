from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional
import uuid
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.core.exceptions import BadRequestException, NotFoundException
from app.modules.audit.models import AuditLog
from app.modules.users.models import User

AUDIT_SORT_FIELDS = {
    "created_at": AuditLog.created_at,
    "action": AuditLog.action,
    "entity_type": AuditLog.entity_type,
}


def _normalize_dt(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _make_json_safe(val: Any) -> Any:
    """Recursively convert datetime, date, UUID, and set instances into JSON-serializable primitives."""
    if isinstance(val, (datetime, date)):
        return val.isoformat()
    if isinstance(val, uuid.UUID):
        return str(val)
    if isinstance(val, dict):
        return {str(k): _make_json_safe(v) for k, v in val.items()}
    if isinstance(val, (list, tuple, set)):
        return [_make_json_safe(v) for v in val]
    return val


class AuditLogRepository:
    def __init__(self, db: AsyncSession, organization_id: str):
        self.db = db
        self.org_id = organization_id

    async def create_log(
        self,
        action: str,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        user_id: Optional[str] = None,
        changes: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> AuditLog:
        """Create and commit an immutable audit log entry scoped to this organization."""
        valid_user_id = None
        if user_id:
            # Check if user exists in the current organization to prevent foreign key errors
            user_stmt = select(User.id).where(
                User.id == str(user_id).strip(),
                User.organization_id == self.org_id,
            )
            if (await self.db.execute(user_stmt)).scalar_one_or_none():
                valid_user_id = str(user_id).strip()

        safe_changes = _make_json_safe(changes) if changes else {}

        audit_entry = AuditLog(
            organization_id=self.org_id,
            user_id=valid_user_id,
            action=action.strip(),
            entity_type=entity_type.strip() if entity_type else None,
            entity_id=entity_id.strip() if entity_id else None,
            changes=safe_changes,
            ip_address=ip_address.strip() if ip_address else None,
            user_agent=user_agent.strip() if user_agent else None,
        )
        self.db.add(audit_entry)
        await self.db.commit()
        await self.db.refresh(audit_entry)
        return audit_entry

    async def get_by_id(self, audit_id: str) -> Optional[AuditLog]:
        """Retrieve a single audit log entry by ID, strictly organization-scoped."""
        stmt = (
            select(AuditLog)
            .where(AuditLog.id == audit_id, AuditLog.organization_id == self.org_id)
            .options(selectinload(AuditLog.user))
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_all(
        self,
        user_id: Optional[str] = None,
        action: Optional[str] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        search: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        sort_by: Optional[str] = None,
        sort_order: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[AuditLog]:
        """List audit logs with comprehensive filtering, search, sorting, and pagination."""
        if start_date and end_date and _normalize_dt(start_date) > _normalize_dt(end_date):
            raise BadRequestException("Start date cannot be after end date.")

        stmt = (
            select(AuditLog)
            .where(AuditLog.organization_id == self.org_id)
            .options(selectinload(AuditLog.user))
        )

        if user_id and user_id.strip():
            stmt = stmt.where(AuditLog.user_id == user_id.strip())
        if action and action.strip():
            stmt = stmt.where(AuditLog.action == action.strip())
        if entity_type and entity_type.strip():
            stmt = stmt.where(AuditLog.entity_type == entity_type.strip())
        if entity_id and entity_id.strip():
            stmt = stmt.where(AuditLog.entity_id == entity_id.strip())

        if start_date:
            stmt = stmt.where(AuditLog.created_at >= start_date)
        if end_date:
            stmt = stmt.where(AuditLog.created_at <= end_date)

        # Search across action, entity_type, and entity_id
        if search and search.strip():
            term = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    AuditLog.action.ilike(term),
                    AuditLog.entity_type.ilike(term),
                    AuditLog.entity_id.ilike(term),
                )
            )

        # Dynamic Sorting (default: created_at desc, secondary id asc)
        clean_sort_by = sort_by.strip().lower() if sort_by and sort_by.strip() else None
        clean_sort_order = sort_order.strip().lower() if sort_order and sort_order.strip() else None

        if clean_sort_order is not None and clean_sort_order not in ("asc", "desc"):
            raise BadRequestException("Invalid sort order. Must be 'asc' or 'desc'.")

        direction = clean_sort_order if clean_sort_order else "desc"

        if clean_sort_by is not None:
            if clean_sort_by not in AUDIT_SORT_FIELDS:
                allowed = ", ".join(sorted(AUDIT_SORT_FIELDS.keys()))
                raise BadRequestException(f"Invalid sort field '{clean_sort_by}'. Allowed fields: {allowed}")
            col = AUDIT_SORT_FIELDS[clean_sort_by]
            stmt = stmt.order_by(col.desc() if direction == "desc" else col.asc(), AuditLog.id.asc())
        else:
            stmt = stmt.order_by(
                AuditLog.created_at.desc() if direction == "desc" else AuditLog.created_at.asc(),
                AuditLog.id.asc(),
            )

        stmt = stmt.offset(offset).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
