from datetime import datetime
from typing import Any, List, Optional
from pydantic import BaseModel, ConfigDict, Field
from app.modules.deals.schemas import DealResponse


class PipelineStageBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    order: int = 1
    win_probability: int = Field(0, ge=0, le=100)
    is_won: bool = False
    is_lost: bool = False


class PipelineStageCreate(PipelineStageBase):
    pass


class PipelineStageUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    order: Optional[int] = None
    win_probability: Optional[int] = Field(None, ge=0, le=100)
    is_won: Optional[bool] = None
    is_lost: Optional[bool] = None


class PipelineStageResponse(PipelineStageBase):
    id: str
    pipeline_id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PipelineBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=150)
    is_default: bool = False


class PipelineCreate(PipelineBase):
    stages: Optional[List[PipelineStageCreate]] = None


class PipelineUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=150)
    is_default: Optional[bool] = None


class PipelineResponse(PipelineBase):
    id: str
    organization_id: str
    stages: List[PipelineStageResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PipelineBoardStageResponse(BaseModel):
    """Stage column on the pipeline Kanban board with aggregated metrics and deals."""
    id: str
    name: str
    order: int
    win_probability: int
    is_won: bool
    is_lost: bool
    deal_count: int = Field(0, description="Total matching deals in this stage across complete dataset")
    total_value: float = Field(0.0, description="Total monetary value of matching deals in this stage across complete dataset")
    deals: List[DealResponse] = Field(default_factory=list, description="Paginated/capped deals in this stage for board display")

    model_config = ConfigDict(from_attributes=True)


class PipelineBoardResponse(BaseModel):
    """Full pipeline Kanban board response with ordered stages, metrics, and deal cards."""
    pipeline_id: str
    pipeline_name: str
    is_default: bool
    total_deals: int = Field(0, description="Total matching deals in the pipeline across all stages")
    total_value: float = Field(0.0, description="Total monetary value of matching deals across all stages")
    stages: List[PipelineBoardStageResponse] = Field(default_factory=list, description="All stages in the pipeline in order")

    model_config = ConfigDict(from_attributes=True)
