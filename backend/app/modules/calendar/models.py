from sqlalchemy import Column, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import relationship
from app.core.database import Base, TenantMixin, TimestampMixin, generate_uuid


class CalendarEvent(Base, TimestampMixin, TenantMixin):
    """Calendar meeting or event synchronized with external calendar providers."""
    __tablename__ = "calendar_events"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    lead_id = Column(String(36), ForeignKey("leads.id", ondelete="CASCADE"), nullable=True, index=True)
    contact_id = Column(String(36), ForeignKey("contacts.id", ondelete="CASCADE"), nullable=True, index=True)
    deal_id = Column(String(36), ForeignKey("deals.id", ondelete="CASCADE"), nullable=True, index=True)

    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    start_time = Column(DateTime(timezone=True), nullable=False, index=True)
    end_time = Column(DateTime(timezone=True), nullable=False)
    location = Column(String(255), nullable=True)
    meeting_link = Column(String(500), nullable=True)
    external_event_id = Column(String(255), nullable=True, index=True)
    provider = Column(String(50), default="google", nullable=False)

    __table_args__ = (
        Index("ix_calendar_events_org_start", "organization_id", "start_time"),
    )

    # Relationships
    organization = relationship("Organization", back_populates="calendar_events")
    lead = relationship("Lead", back_populates="calendar_events")
