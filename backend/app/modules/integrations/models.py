from sqlalchemy import Boolean, Column, Index, JSON, String
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
