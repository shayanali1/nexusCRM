from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.exceptions import NotFoundException
from app.core.permissions import Permission
from app.modules.auth.dependencies import get_current_user, require_permission
from app.modules.pipelines.models import Pipeline
from app.modules.pipelines.repository import PipelineRepository
from app.modules.pipelines.schemas import (
    PipelineBoardResponse,
    PipelineCreate,
    PipelineResponse,
    PipelineStageCreate,
    PipelineStageResponse,
    PipelineStageUpdate,
    PipelineUpdate,
)
from app.modules.users.models import User

router = APIRouter(prefix="/pipelines", tags=["Pipelines"])


@router.get("", response_model=List[PipelineResponse])
async def list_pipelines(
    current_user: User = Depends(require_permission(Permission.DEALS_READ)),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve all sales pipelines and their ordered stages."""
    repo = PipelineRepository(db, current_user.organization_id)
    pipelines = await repo.list_all()
    return [PipelineResponse.model_validate(p) for p in pipelines]


@router.post("", response_model=PipelineResponse, status_code=status.HTTP_201_CREATED)
async def create_pipeline(
    req: PipelineCreate,
    current_user: User = Depends(require_permission(Permission.PIPELINES_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    """Create a new sales pipeline."""
    repo = PipelineRepository(db, current_user.organization_id)
    pipeline = await repo.create(req)
    loaded = await repo.get_by_id(pipeline.id)
    return PipelineResponse.model_validate(loaded or pipeline)


@router.get("/{pipeline_id}", response_model=PipelineResponse)
async def get_pipeline(
    pipeline_id: str,
    current_user: User = Depends(require_permission(Permission.DEALS_READ)),
    db: AsyncSession = Depends(get_db),
):
    """Get single sales pipeline with stages."""
    repo = PipelineRepository(db, current_user.organization_id)
    pipeline = await repo.get_by_id(pipeline_id)
    if not pipeline:
        raise NotFoundException("Pipeline not found.")
    return PipelineResponse.model_validate(pipeline)


@router.get("/{pipeline_id}/board", response_model=PipelineBoardResponse)
async def get_pipeline_board(
    pipeline_id: str,
    assigned_to_id: Optional[str] = Query(None, description="Filter deals by salesperson"),
    status: Optional[str] = Query(None, description="Filter deals by status (OPEN, WON, LOST)"),
    search: Optional[str] = Query(None, description="Search deal title"),
    limit_per_stage: int = Query(50, ge=1, le=200, description="Max deals returned per stage"),
    current_user: User = Depends(require_permission(Permission.DEALS_READ)),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve deals for a selected pipeline grouped by stage with accurate per-stage metrics."""
    repo = PipelineRepository(db, current_user.organization_id)
    return await repo.get_board(
        pipeline_id=pipeline_id,
        assigned_to_id=assigned_to_id,
        status=status,
        search=search,
        limit_per_stage=limit_per_stage,
    )


@router.patch("/{pipeline_id}", response_model=PipelineResponse)
async def update_pipeline(
    pipeline_id: str,
    req: PipelineUpdate,
    current_user: User = Depends(require_permission(Permission.PIPELINES_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    """Update a sales pipeline name or default status."""
    repo = PipelineRepository(db, current_user.organization_id)
    pipeline = await repo.get_by_id(pipeline_id)
    if not pipeline:
        raise NotFoundException("Pipeline not found.")
    updated = await repo.update(pipeline, req)
    return PipelineResponse.model_validate(updated)


@router.delete("/{pipeline_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_pipeline(
    pipeline_id: str,
    current_user: User = Depends(require_permission(Permission.PIPELINES_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    """Delete an empty, non-default sales pipeline."""
    repo = PipelineRepository(db, current_user.organization_id)
    pipeline = await repo.get_by_id(pipeline_id)
    if not pipeline:
        raise NotFoundException("Pipeline not found.")
    await repo.delete(pipeline)


@router.post("/{pipeline_id}/stages", response_model=PipelineStageResponse, status_code=status.HTTP_201_CREATED)
async def add_stage_to_pipeline(
    pipeline_id: str,
    req: PipelineStageCreate,
    current_user: User = Depends(require_permission(Permission.PIPELINES_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    """Add a new stage into an existing pipeline."""
    repo = PipelineRepository(db, current_user.organization_id)
    pipeline = await repo.get_by_id(pipeline_id)
    if not pipeline:
        raise NotFoundException("Pipeline not found.")
    stage = await repo.add_stage(pipeline_id, req)
    return PipelineStageResponse.model_validate(stage)


@router.patch("/{pipeline_id}/stages/{stage_id}", response_model=PipelineStageResponse)
async def update_pipeline_stage(
    pipeline_id: str,
    stage_id: str,
    req: PipelineStageUpdate,
    current_user: User = Depends(require_permission(Permission.PIPELINES_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    """Update a stage's name, order, win probability, or won/lost flag."""
    repo = PipelineRepository(db, current_user.organization_id)
    stage = await repo.get_stage_by_id(pipeline_id, stage_id)
    if not stage:
        raise NotFoundException("Pipeline stage not found.")
    updated = await repo.update_stage(stage, req)
    return PipelineStageResponse.model_validate(updated)


@router.delete("/{pipeline_id}/stages/{stage_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_pipeline_stage(
    pipeline_id: str,
    stage_id: str,
    current_user: User = Depends(require_permission(Permission.PIPELINES_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    """Delete an empty stage from a sales pipeline."""
    repo = PipelineRepository(db, current_user.organization_id)
    stage = await repo.get_stage_by_id(pipeline_id, stage_id)
    if not stage:
        raise NotFoundException("Pipeline stage not found.")
    await repo.delete_stage(stage)
