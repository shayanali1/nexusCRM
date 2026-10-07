from sqlalchemy import Boolean, Column, ForeignKey, Index, Integer, String
from sqlalchemy.orm import relationship
from app.core.database import Base, TenantMixin, TimestampMixin, generate_uuid


class Pipeline(Base, TimestampMixin, TenantMixin):
    """Sales Pipeline container representing a sales workflow."""
    __tablename__ = "pipelines"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(150), nullable=False)
    is_default = Column(Boolean, default=False, nullable=False)

    __table_args__ = (
        Index("ix_pipelines_org_default", "organization_id", "is_default"),
    )

    # Relationships
    organization = relationship("Organization", back_populates="pipelines")
    stages = relationship("PipelineStage", back_populates="pipeline", cascade="all, delete-orphan", order_by="PipelineStage.order")
    deals = relationship("Deal", back_populates="pipeline")


class PipelineStage(Base, TimestampMixin, TenantMixin):
    """Specific stage inside a sales pipeline."""
    __tablename__ = "pipeline_stages"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    pipeline_id = Column(String(36), ForeignKey("pipelines.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    order = Column(Integer, default=1, nullable=False)
    win_probability = Column(Integer, default=0, nullable=False)  # 0 to 100%
    is_won = Column(Boolean, default=False, nullable=False)
    is_lost = Column(Boolean, default=False, nullable=False)

    __table_args__ = (
        Index("ix_pipeline_stages_pipeline_order", "pipeline_id", "order"),
    )

    # Relationships
    pipeline = relationship("Pipeline", back_populates="stages")
    deals = relationship("Deal", back_populates="stage")
