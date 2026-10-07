from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, JSON, String, Text
from sqlalchemy.orm import relationship
from app.core.database import Base, TenantMixin, TimestampMixin, generate_uuid


class Notification(Base, TimestampMixin, TenantMixin):
    """User in-app notification entity."""
    __tablename__ = "notifications"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    notification_type = Column(String(50), default="INFO", nullable=False)  # "TASK_DUE", "LEAD_ASSIGNED", "AI_INSIGHT", "DEAL_WON"
    is_read = Column(Boolean, default=False, nullable=False, index=True)
    read_at = Column(DateTime(timezone=True), nullable=True)
    link = Column(String(500), nullable=True)
    extra_metadata = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        Index("ix_notifications_user_read", "user_id", "is_read"),
    )

    # Relationships
    organization = relationship("Organization", back_populates="notifications")
    user = relationship("User", back_populates="notifications")
