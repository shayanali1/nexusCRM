from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, String, JSON
from sqlalchemy.orm import relationship
from app.core.database import Base, TenantMixin, TimestampMixin, generate_uuid
from app.core.permissions import RoleEnum


class User(Base, TimestampMixin, TenantMixin):
    """User account within an Organization."""
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    email = Column(String(255), nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    role = Column(String(50), default=RoleEnum.MEMBER.value, nullable=False, index=True)
    phone = Column(String(50), nullable=True)
    avatar_url = Column(String(1024), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    last_login_at = Column(DateTime(timezone=True), nullable=True)

    # Scoped unique constraint: An email is unique per organization
    __table_args__ = (
        Index("ix_users_org_email", "organization_id", "email", unique=True),
    )

    # Relationships
    organization = relationship("Organization", back_populates="users")
    assigned_leads = relationship("Lead", back_populates="assigned_to", foreign_keys="Lead.assigned_to_id")
    assigned_deals = relationship("Deal", back_populates="assigned_to", foreign_keys="Deal.assigned_to_id")
    assigned_tasks = relationship("Task", back_populates="assigned_to", foreign_keys="Task.assigned_to_id")
    created_tasks = relationship("Task", back_populates="created_by", foreign_keys="Task.created_by_id")
    activities = relationship("Activity", back_populates="user")
    notifications = relationship("Notification", back_populates="user", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="user")

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()


class Role(Base, TimestampMixin, TenantMixin):
    """Customizable role definition per organization."""
    __tablename__ = "roles"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(100), nullable=False)
    description = Column(String(255), nullable=True)
    permissions = Column(JSON, default=list, nullable=False)
