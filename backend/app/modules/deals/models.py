from enum import Enum
from sqlalchemy import Column, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.orm import relationship
from app.core.database import Base, TenantMixin, TimestampMixin, generate_uuid


class DealStatus(str, Enum):
    OPEN = "OPEN"
    WON = "WON"
    LOST = "LOST"


class Deal(Base, TimestampMixin, TenantMixin):
    """Deal entity tracking sales opportunities and revenue in the pipeline."""
    __tablename__ = "deals"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    pipeline_id = Column(String(36), ForeignKey("pipelines.id", ondelete="RESTRICT"), nullable=False, index=True)
    stage_id = Column(String(36), ForeignKey("pipeline_stages.id", ondelete="RESTRICT"), nullable=False, index=True)
    contact_id = Column(String(36), ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True, index=True)
    company_id = Column(String(36), ForeignKey("companies.id", ondelete="SET NULL"), nullable=True, index=True)
    assigned_to_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    title = Column(String(255), nullable=False)
    value = Column(Float, default=0.0, nullable=False)
    currency = Column(String(10), default="USD", nullable=False)
    status = Column(String(50), default=DealStatus.OPEN.value, nullable=False, index=True)
    win_probability = Column(Integer, default=50, nullable=False)
    expected_close_date = Column(DateTime(timezone=True), nullable=True)
    closed_at = Column(DateTime(timezone=True), nullable=True)
    lost_reason = Column(String(255), nullable=True)
    notes = Column(Text, nullable=True)
    custom_fields = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        Index("ix_deals_org_status", "organization_id", "status"),
        Index("ix_deals_org_stage", "organization_id", "stage_id"),
        Index("ix_deals_org_assigned", "organization_id", "assigned_to_id"),
    )

    # Relationships
    organization = relationship("Organization", back_populates="deals")
    pipeline = relationship("Pipeline", back_populates="deals")
    stage = relationship("PipelineStage", back_populates="deals")
    contact = relationship("Contact", back_populates="deals")
    company = relationship("Company", back_populates="deals")
    assigned_to = relationship("User", back_populates="assigned_deals", foreign_keys=[assigned_to_id])
    activities = relationship("Activity", back_populates="deal", cascade="all, delete-orphan")
    tasks = relationship("Task", back_populates="deal", cascade="all, delete-orphan")
