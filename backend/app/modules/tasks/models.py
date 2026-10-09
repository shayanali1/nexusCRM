from enum import Enum
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, JSON, String, Text
from sqlalchemy.orm import relationship
from app.core.database import Base, TenantMixin, TimestampMixin, generate_uuid


class TaskPriority(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    URGENT = "URGENT"


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class TaskType(str, Enum):
    FOLLOW_UP = "FOLLOW_UP"
    CALL = "CALL"
    EMAIL = "EMAIL"
    MEETING = "MEETING"
    PROPOSAL_REVIEW = "PROPOSAL_REVIEW"
    DEMO = "DEMO"
    OTHER = "OTHER"


class Task(Base, TimestampMixin, TenantMixin):
    """Task and explicit follow-up entity tied to leads, contacts, or deals."""
    __tablename__ = "tasks"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    assigned_to_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_by_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    lead_id = Column(String(36), ForeignKey("leads.id", ondelete="CASCADE"), nullable=True, index=True)
    contact_id = Column(String(36), ForeignKey("contacts.id", ondelete="CASCADE"), nullable=True, index=True)
    deal_id = Column(String(36), ForeignKey("deals.id", ondelete="CASCADE"), nullable=True, index=True)

    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    task_type = Column(String(50), default=TaskType.FOLLOW_UP.value, nullable=False)
    priority = Column(String(50), default=TaskPriority.MEDIUM.value, nullable=False, index=True)
    status = Column(String(50), default=TaskStatus.PENDING.value, nullable=False, index=True)
    due_date = Column(DateTime(timezone=True), nullable=False, index=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    extra_metadata = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        Index("ix_tasks_org_due", "organization_id", "due_date"),
        Index("ix_tasks_org_status", "organization_id", "status"),
        Index("ix_tasks_org_assigned", "organization_id", "assigned_to_id"),
    )

    # Relationships
    organization = relationship("Organization", back_populates="tasks")
    assigned_to = relationship("User", back_populates="assigned_tasks", foreign_keys=[assigned_to_id])
    created_by = relationship("User", back_populates="created_tasks", foreign_keys=[created_by_id])
    lead = relationship("Lead", back_populates="tasks")
    contact = relationship("Contact", back_populates="tasks")
    deal = relationship("Deal", back_populates="tasks")
