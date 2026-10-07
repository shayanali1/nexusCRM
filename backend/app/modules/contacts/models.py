from sqlalchemy import Column, ForeignKey, Index, JSON, String
from sqlalchemy.orm import relationship
from app.core.database import Base, TenantMixin, TimestampMixin, generate_uuid


class Contact(Base, TimestampMixin, TenantMixin):
    """Customer or individual contact in NexusCRM."""
    __tablename__ = "contacts"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    company_id = Column(String(36), ForeignKey("companies.id", ondelete="SET NULL"), nullable=True, index=True)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    email = Column(String(255), nullable=True, index=True)
    phone = Column(String(50), nullable=True, index=True)
    title = Column(String(150), nullable=True)  # Job title
    lead_source = Column(String(100), nullable=True)  # Website, WhatsApp, Referral, Cold Outreach
    address = Column(String(500), nullable=True)
    custom_fields = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        Index("ix_contacts_org_email", "organization_id", "email"),
        Index("ix_contacts_org_name", "organization_id", "last_name", "first_name"),
    )

    # Relationships
    organization = relationship("Organization", back_populates="contacts")
    company = relationship("Company", back_populates="contacts")
    leads = relationship("Lead", back_populates="contact")
    deals = relationship("Deal", back_populates="contact")
    activities = relationship("Activity", back_populates="contact")
    tasks = relationship("Task", back_populates="contact")

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()
