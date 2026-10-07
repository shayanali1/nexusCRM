from sqlalchemy import Column, ForeignKey, Index, JSON, String, Text
from sqlalchemy.orm import relationship
from app.core.database import Base, TenantMixin, TimestampMixin, generate_uuid


class AuditLog(Base, TimestampMixin, TenantMixin):
    """Immutable audit trail of user and system actions within an organization."""
    __tablename__ = "audit_logs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    action = Column(String(100), nullable=False, index=True)  # e.g., "lead.created", "deal.won", "user.login"
    entity_type = Column(String(50), nullable=True, index=True)
    entity_id = Column(String(36), nullable=True, index=True)
    changes = Column(JSON, default=dict, nullable=False)
    ip_address = Column(String(50), nullable=True)
    user_agent = Column(String(500), nullable=True)

    __table_args__ = (
        Index("ix_audit_logs_org_created", "organization_id", "created_at"),
    )

    # Relationships
    organization = relationship("Organization", back_populates="audit_logs")
    user = relationship("User", back_populates="audit_logs")
