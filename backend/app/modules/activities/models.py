from enum import Enum
from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.orm import relationship
from app.core.database import Base, TenantMixin, TimestampMixin, generate_uuid


class ActivityType(str, Enum):
    CALL = "CALL"
    EMAIL = "EMAIL"
    MEETING = "MEETING"
    NOTE = "NOTE"
    PROPOSAL = "PROPOSAL"
    STAGE_CHANGE = "STAGE_CHANGE"
    TASK_COMPLETED = "TASK_COMPLETED"
    SYSTEM = "SYSTEM"


class Activity(Base, TimestampMixin, TenantMixin):
    """Chronological interaction/event recorded against a Lead, Contact, or Deal."""
    __tablename__ = "activities"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    lead_id = Column(String(36), ForeignKey("leads.id", ondelete="CASCADE"), nullable=True, index=True)
    contact_id = Column(String(36), ForeignKey("contacts.id", ondelete="CASCADE"), nullable=True, index=True)
    deal_id = Column(String(36), ForeignKey("deals.id", ondelete="CASCADE"), nullable=True, index=True)

    activity_type = Column(String(50), default=ActivityType.NOTE.value, nullable=False, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    outcome = Column(String(100), nullable=True)  # e.g., "Connected", "Left Voicemail", "Interested", "Rescheduled"
    duration_seconds = Column(Integer, default=0, nullable=False)
    performed_at = Column(DateTime(timezone=True), nullable=False)
    extra_metadata = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        Index("ix_activities_org_performed", "organization_id", "performed_at"),
        Index("ix_activities_org_type", "organization_id", "activity_type"),
    )

    # Relationships
    organization = relationship("Organization", back_populates="activities")
    user = relationship("User", back_populates="activities")
    lead = relationship("Lead", back_populates="activities")
    contact = relationship("Contact", back_populates="activities")
    deal = relationship("Deal", back_populates="activities")
