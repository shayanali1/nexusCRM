from typing import List
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.exceptions import NotFoundException
from app.core.permissions import Permission
from app.modules.auth.dependencies import get_current_user, require_permission
from app.modules.pipelines.models import Pipeline
from app.modules.pipelines.repository import PipelineRepository
from app.modules.pipelines.schemas import PipelineCreate, PipelineResponse, PipelineStageCreate, PipelineStageResponse
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
