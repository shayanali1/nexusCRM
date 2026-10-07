from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


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
