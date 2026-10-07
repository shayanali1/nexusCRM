from enum import Enum
from sqlalchemy import Column, Float, ForeignKey, Index, Integer, JSON, String, Text, DateTime
from sqlalchemy.orm import relationship
from app.core.database import Base, TenantMixin, TimestampMixin, generate_uuid


class LeadStatus(str, Enum):
    NEW = "NEW"
    CONTACTED = "CONTACTED"
    QUALIFIED = "QUALIFIED"
    INTERESTED = "INTERESTED"
    PROPOSAL = "PROPOSAL"
    NEGOTIATION = "NEGOTIATION"
    WON = "WON"
    LOST = "LOST"


class LeadPriority(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    URGENT = "URGENT"


class Lead(Base, TimestampMixin, TenantMixin):
    """Lead entity managing prospective customers through the sales lifecycle."""
    __tablename__ = "leads"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    contact_id = Column(String(36), ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True, index=True)
    company_id = Column(String(36), ForeignKey("companies.id", ondelete="SET NULL"), nullable=True, index=True)
    assigned_to_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    title = Column(String(255), nullable=False)
    status = Column(String(50), default=LeadStatus.NEW.value, nullable=False, index=True)
    source = Column(String(100), default="Website", nullable=False, index=True)
    score = Column(Integer, default=50, nullable=False)
    priority = Column(String(50), default=LeadPriority.MEDIUM.value, nullable=False, index=True)
    estimated_value = Column(Float, default=0.0, nullable=False)
    currency = Column(String(10), default="USD", nullable=False)

    lost_reason = Column(String(255), nullable=True)
    notes = Column(Text, nullable=True)
    custom_fields = Column(JSON, default=dict, nullable=False)

    converted_at = Column(DateTime(timezone=True), nullable=True)
    converted_to_deal_id = Column(String(36), ForeignKey("deals.id", ondelete="SET NULL"), nullable=True)

    __table_args__ = (
        Index("ix_leads_org_status", "organization_id", "status"),
        Index("ix_leads_org_assigned", "organization_id", "assigned_to_id"),
        Index("ix_leads_org_priority", "organization_id", "priority"),
    )

    # Relationships
    organization = relationship("Organization", back_populates="leads")
    contact = relationship("Contact", back_populates="leads")
    company = relationship("Company", back_populates="leads")
    assigned_to = relationship("User", back_populates="assigned_leads", foreign_keys=[assigned_to_id])
    activities = relationship("Activity", back_populates="lead", cascade="all, delete-orphan")
    tasks = relationship("Task", back_populates="lead", cascade="all, delete-orphan")
    calendar_events = relationship("CalendarEvent", back_populates="lead", cascade="all, delete-orphan")
