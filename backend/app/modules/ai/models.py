from enum import Enum
from sqlalchemy import Column, Float, ForeignKey, Index, JSON, String, Text
from sqlalchemy.orm import relationship
from app.core.database import Base, TenantMixin, TimestampMixin, generate_uuid


class InsightType(str, Enum):
    SUMMARY = "SUMMARY"
    NEXT_ACTION = "NEXT_ACTION"
    PRIORITY_SCORE = "PRIORITY_SCORE"
    MESSAGE_DRAFT = "MESSAGE_DRAFT"
    DEAL_GUIDANCE = "DEAL_GUIDANCE"


class AIJobStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class AIInsight(Base, TimestampMixin, TenantMixin):
    """Cached AI-generated intelligence record for CRM entities."""
    __tablename__ = "ai_insights"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    entity_type = Column(String(50), nullable=False, index=True)  # "lead", "contact", "deal", "company"
    entity_id = Column(String(36), nullable=False, index=True)
    insight_type = Column(String(50), nullable=False, index=True)
    content = Column(JSON, default=dict, nullable=False)
    confidence = Column(Float, default=1.0, nullable=False)
    model_name = Column(String(100), default="mock-ai-engine", nullable=False)
    provider_name = Column(String(50), default="mock", nullable=False)

    __table_args__ = (
        Index("ix_ai_insights_lookup", "organization_id", "entity_type", "entity_id", "insight_type"),
    )

    # Relationships
    organization = relationship("Organization", back_populates="ai_insights")


class AIJob(Base, TimestampMixin, TenantMixin):
    """Asynchronous background AI task record."""
    __tablename__ = "ai_jobs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    task_type = Column(String(100), nullable=False, index=True)
    status = Column(String(50), default=AIJobStatus.PENDING.value, nullable=False, index=True)
    payload = Column(JSON, default=dict, nullable=False)
    result = Column(JSON, default=dict, nullable=True)
    error_message = Column(Text, nullable=True)
