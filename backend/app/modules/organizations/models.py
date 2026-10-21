from sqlalchemy import Boolean, Column, JSON, String
from sqlalchemy.orm import relationship
from app.core.database import Base, TimestampMixin, generate_uuid


class Organization(Base, TimestampMixin):
    """Top-level tenant boundary in NexusCRM."""
    __tablename__ = "organizations"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(255), nullable=False)
    slug = Column(String(100), unique=True, nullable=False, index=True)
    domain = Column(String(255), nullable=True)
    logo_url = Column(String(1024), nullable=True)
    plan = Column(String(50), default="starter", nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    settings = Column(JSON, default=dict, nullable=False)

    # Relationships
    users = relationship("User", back_populates="organization", cascade="all, delete-orphan")
    contacts = relationship("Contact", back_populates="organization", cascade="all, delete-orphan")
    companies = relationship("Company", back_populates="organization", cascade="all, delete-orphan")
    leads = relationship("Lead", back_populates="organization", cascade="all, delete-orphan")
    pipelines = relationship("Pipeline", back_populates="organization", cascade="all, delete-orphan")
    deals = relationship("Deal", back_populates="organization", cascade="all, delete-orphan")
    activities = relationship("Activity", back_populates="organization", cascade="all, delete-orphan")
    tasks = relationship("Task", back_populates="organization", cascade="all, delete-orphan")
    calendar_events = relationship("CalendarEvent", back_populates="organization", cascade="all, delete-orphan")
    automation_rules = relationship("AutomationRule", back_populates="organization", cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="organization", cascade="all, delete-orphan")
    ai_insights = relationship("AIInsight", back_populates="organization", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="organization", cascade="all, delete-orphan")
    integrations = relationship("Integration", back_populates="organization", cascade="all, delete-orphan")
    webhook_subscriptions = relationship("WebhookSubscription", back_populates="organization", cascade="all, delete-orphan")
    webhook_deliveries = relationship("WebhookDelivery", back_populates="organization", cascade="all, delete-orphan")
