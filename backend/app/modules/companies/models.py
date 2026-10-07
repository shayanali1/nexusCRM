from sqlalchemy import Column, Index, JSON, String
from sqlalchemy.orm import relationship
from app.core.database import Base, TenantMixin, TimestampMixin, generate_uuid


class Company(Base, TimestampMixin, TenantMixin):
    """Business account entity in NexusCRM."""
    __tablename__ = "companies"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(255), nullable=False, index=True)
    domain = Column(String(255), nullable=True, index=True)
    industry = Column(String(100), nullable=True)
    size = Column(String(50), nullable=True)  # e.g., 1-10, 11-50, 51-200, 200+
    phone = Column(String(50), nullable=True)
    website = Column(String(500), nullable=True)
    address = Column(String(500), nullable=True)
    city = Column(String(100), nullable=True)
    country = Column(String(100), nullable=True)
    custom_fields = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        Index("ix_companies_org_name", "organization_id", "name"),
    )

    # Relationships
    organization = relationship("Organization", back_populates="companies")
    contacts = relationship("Contact", back_populates="company", cascade="all, delete-orphan")
    leads = relationship("Lead", back_populates="company")
    deals = relationship("Deal", back_populates="company")
