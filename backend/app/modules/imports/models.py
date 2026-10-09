from sqlalchemy import Column, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.orm import relationship
from app.core.database import Base, TenantMixin, TimestampMixin, generate_uuid


class ImportJob(Base, TimestampMixin, TenantMixin):
    """Batch data import job record (CSV/XLSX)."""
    __tablename__ = "import_jobs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    entity_type = Column(String(50), nullable=False)  # "leads", "contacts", "companies"
    file_name = Column(String(255), nullable=False)
    file_path = Column(String(1024), nullable=False)
    status = Column(String(50), default="PENDING", nullable=False, index=True)  # PENDING, PROCESSING, COMPLETED, FAILED
    total_rows = Column(Integer, default=0, nullable=False)
    processed_rows = Column(Integer, default=0, nullable=False)
    successful_rows = Column(Integer, default=0, nullable=False)
    failed_rows = Column(Integer, default=0, nullable=False)
    duplicate_rows = Column(Integer, default=0, nullable=False)
    errors = Column(JSON, default=list, nullable=False)

    # Relationships
    rows = relationship("ImportRow", back_populates="import_job", cascade="all, delete-orphan")


class ImportRow(Base, TimestampMixin):
    """Detailed row log for validation and error auditing during CSV import."""
    __tablename__ = "import_rows"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    import_job_id = Column(String(36), ForeignKey("import_jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    row_number = Column(Integer, nullable=False)
    raw_data = Column(JSON, default=dict, nullable=False)
    status = Column(String(50), default="PENDING", nullable=False)  # PENDING, SUCCESS, ERROR, DUPLICATE
    error_message = Column(Text, nullable=True)

    # Relationships
    import_job = relationship("ImportJob", back_populates="rows")
