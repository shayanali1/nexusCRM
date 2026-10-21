from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKeyConstraint,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from app.core.database import Base, TenantMixin, TimestampMixin, generate_uuid


class Integration(Base, TimestampMixin, TenantMixin):
    """External third-party integration configuration."""
    __tablename__ = "integrations"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    provider = Column(String(100), nullable=False)  # "google_calendar", "sendgrid", "resend", "slack", "zapier"
    is_active = Column(Boolean, default=False, nullable=False)
    config = Column(JSON, default=dict, nullable=False)
    credentials = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        Index("ix_integrations_org_provider", "organization_id", "provider", unique=True),
    )

    # Relationships
    organization = relationship("Organization", back_populates="integrations")


class WebhookSubscription(Base, TimestampMixin, TenantMixin):
    """Outbound webhook subscription configured by an organization."""
    __tablename__ = "webhook_subscriptions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(255), nullable=False)
    url = Column(String(2048), nullable=False)
    events = Column(JSON, default=list, nullable=False)
    secret = Column(JSON, default=dict, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    consecutive_failures = Column(Integer, default=0, nullable=False)

    __table_args__ = (
        UniqueConstraint("id", "organization_id", name="uq_webhook_subscriptions_id_org"),
        Index("ix_webhook_subscriptions_org_active", "organization_id", "is_active"),
        Index("ix_webhook_subscriptions_org_name", "organization_id", "name"),
    )

    # Relationships
    organization = relationship("Organization", back_populates="webhook_subscriptions")
    deliveries = relationship(
        "WebhookDelivery",
        back_populates="subscription",
        cascade="all, delete-orphan",
        foreign_keys="[WebhookDelivery.subscription_id, WebhookDelivery.organization_id]",
        overlaps="webhook_deliveries",
    )


class WebhookDelivery(Base, TimestampMixin, TenantMixin):
    """Individual outbound webhook delivery attempt / log."""
    __tablename__ = "webhook_deliveries"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    subscription_id = Column(String(36), nullable=False)
    event_type = Column(String(100), nullable=False, index=True)
    event_id = Column(String(100), nullable=False, index=True)
    payload = Column(JSON, default=dict, nullable=False)
    status = Column(String(20), default="pending", nullable=False, index=True)
    attempt_count = Column(Integer, default=0, nullable=False)
    response_status_code = Column(Integer, nullable=True)
    response_body = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    execution_time_ms = Column(Float, nullable=True)
    last_attempt_at = Column(DateTime(timezone=True), nullable=True)
    next_retry_at = Column(DateTime(timezone=True), nullable=True)
    delivered_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        ForeignKeyConstraint(
            ["subscription_id", "organization_id"],
            ["webhook_subscriptions.id", "webhook_subscriptions.organization_id"],
            ondelete="CASCADE",
            name="fk_webhook_deliveries_subscription_org",
        ),
        UniqueConstraint("subscription_id", "event_id", name="uq_webhook_deliveries_sub_event"),
        Index("ix_webhook_deliveries_org_status", "organization_id", "status"),
        Index("ix_webhook_deliveries_org_created", "organization_id", "created_at"),
        Index("ix_webhook_deliveries_sub_created", "subscription_id", "created_at"),
    )

    # Relationships
    organization = relationship(
        "Organization",
        back_populates="webhook_deliveries",
        foreign_keys="[WebhookDelivery.organization_id]",
        overlaps="deliveries,subscription",
    )
    subscription = relationship(
        "WebhookSubscription",
        back_populates="deliveries",
        foreign_keys="[WebhookDelivery.subscription_id, WebhookDelivery.organization_id]",
        overlaps="organization,webhook_deliveries",
    )
