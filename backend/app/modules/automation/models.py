from sqlalchemy import Boolean, Column, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.orm import relationship
from app.core.database import Base, TenantMixin, TimestampMixin, generate_uuid


class AutomationRule(Base, TimestampMixin, TenantMixin):
    """Event-Condition-Action automation workflow rule."""
    __tablename__ = "automation_rules"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    event_trigger = Column(String(100), nullable=False, index=True)  # e.g., "lead.created", "deal.won", "task.overdue"
    conditions = Column(JSON, default=list, nullable=False)  # list of {field, operator, value}
    is_active = Column(Boolean, default=True, nullable=False, index=True)

    # Relationships
    organization = relationship("Organization", back_populates="automation_rules")
    actions = relationship("AutomationAction", back_populates="rule", cascade="all, delete-orphan", order_by="AutomationAction.execution_order")


class AutomationAction(Base, TimestampMixin):
    """Individual action executed when an automation rule matches."""
    __tablename__ = "automation_actions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    rule_id = Column(String(36), ForeignKey("automation_rules.id", ondelete="CASCADE"), nullable=False, index=True)
    action_type = Column(String(100), nullable=False)  # "create_task", "assign_user", "send_notification", "create_activity"
    action_config = Column(JSON, default=dict, nullable=False)
    execution_order = Column(Integer, default=1, nullable=False)

    # Relationships
    rule = relationship("AutomationRule", back_populates="actions")
