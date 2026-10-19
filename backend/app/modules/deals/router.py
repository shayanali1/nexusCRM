from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.exceptions import NotFoundException
from app.core.permissions import Permission
from app.modules.auth.dependencies import get_current_user, require_permission
from app.modules.deals.models import Deal
from app.modules.deals.repository import DealRepository
from app.modules.deals.schemas import (
    DealCreate,
    DealResponse,
    DealStageMoveRequest,
    DealUpdate,
    format_deal_response,
)
from app.modules.pipelines.models import Pipeline
from app.modules.pipelines.repository import PipelineRepository
from app.modules.pipelines.schemas import PipelineBoardResponse
from app.modules.users.models import User

router = APIRouter(prefix="/deals", tags=["Deals"])

_to_deal_resp = format_deal_response


@router.get("", response_model=List[DealResponse])
async def list_deals(
    pipeline_id: Optional[str] = Query(None, description="Filter by pipeline"),
    stage_id: Optional[str] = Query(None, description="Filter by stage"),
    status: Optional[str] = Query(None, description="Filter by status (OPEN, WON, LOST)"),
    assigned_to_id: Optional[str] = Query(None, description="Filter by salesperson"),
    search: Optional[str] = Query(None, description="Search deal title"),
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(require_permission(Permission.DEALS_READ)),
    db: AsyncSession = Depends(get_db),
):
    """List all pipeline deals with filter options."""
    repo = DealRepository(db, current_user.organization_id)
    deals = await repo.list_all(pipeline_id, stage_id, status, assigned_to_id, search, limit, offset)
    return [_to_deal_resp(d) for d in deals]


@router.post("", response_model=DealResponse, status_code=status.HTTP_201_CREATED)
async def create_deal(
    req: DealCreate,
    current_user: User = Depends(require_permission(Permission.DEALS_CREATE)),
    db: AsyncSession = Depends(get_db),
):
    """Create a new deal."""
    repo = DealRepository(db, current_user.organization_id)
    deal = await repo.create(req)
    loaded = await repo.get_by_id(deal.id)
    return _to_deal_resp(loaded or deal)


@router.get("/board", response_model=PipelineBoardResponse)
async def get_deals_board(
    pipeline_id: Optional[str] = Query(None, description="Pipeline ID (defaults to default pipeline)"),
    assigned_to_id: Optional[str] = Query(None, description="Filter by salesperson"),
    status: Optional[str] = Query(None, description="Filter by status (OPEN, WON, LOST)"),
    search: Optional[str] = Query(None, description="Search deal title"),
    limit_per_stage: int = Query(50, ge=1, le=200, description="Max deals returned per stage"),
    current_user: User = Depends(require_permission(Permission.DEALS_READ)),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve Kanban board representation for deals (defaults to default pipeline if pipeline_id omitted)."""
    pipe_repo = PipelineRepository(db, current_user.organization_id)
    target_pipe_id = pipeline_id
    if not target_pipe_id:
        def_pipe = (await db.execute(
            select(Pipeline.id).where(
                Pipeline.organization_id == current_user.organization_id,
                Pipeline.is_default.is_(True),
            )
        )).scalars().first()
        if not def_pipe:
            first_pipe = (await db.execute(
                select(Pipeline.id).where(
                    Pipeline.organization_id == current_user.organization_id,
                ).order_by(Pipeline.created_at.asc())
            )).scalars().first()
            if not first_pipe:
                raise NotFoundException("Pipeline not found.")
            target_pipe_id = first_pipe
        else:
            target_pipe_id = def_pipe

    return await pipe_repo.get_board(
        pipeline_id=target_pipe_id,
        assigned_to_id=assigned_to_id,
        status=status,
        search=search,
        limit_per_stage=limit_per_stage,
    )


@router.get("/{deal_id}", response_model=DealResponse)
async def get_deal(
    deal_id: str,
    current_user: User = Depends(require_permission(Permission.DEALS_READ)),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve full details of a deal."""
    repo = DealRepository(db, current_user.organization_id)
    deal = await repo.get_by_id(deal_id)
    if not deal:
        raise NotFoundException("Deal not found.")
    return _to_deal_resp(deal)


@router.patch("/{deal_id}", response_model=DealResponse)
async def update_deal(
    deal_id: str,
    req: DealUpdate,
    current_user: User = Depends(require_permission(Permission.DEALS_UPDATE)),
    db: AsyncSession = Depends(get_db),
):
    """Update deal details."""
    repo = DealRepository(db, current_user.organization_id)
    deal = await repo.get_by_id(deal_id)
    if not deal:
        raise NotFoundException("Deal not found.")
    old_status = deal.status
    updated = await repo.update(deal, req)
    loaded = await repo.get_by_id(updated.id)

    from app.core.events import CRMEvent, CRMEventType, event_dispatcher
    from app.modules.deals.models import DealStatus

    if updated.status == DealStatus.WON.value and old_status != DealStatus.WON.value:
        await event_dispatcher.dispatch(
            CRMEvent(
                event_name=CRMEventType.DEAL_WON,
                organization_id=current_user.organization_id,
                entity_type="deal",
                entity_id=updated.id,
                actor_id=current_user.id,
                payload={"deal_id": updated.id, "title": updated.title, "value": updated.value},
            ),
            db,
        )

    return _to_deal_resp(loaded or updated)


@router.post("/{deal_id}/move-stage", response_model=DealResponse)
async def move_deal_stage(
    deal_id: str,
    req: DealStageMoveRequest,
    current_user: User = Depends(require_permission(Permission.DEALS_UPDATE)),
    db: AsyncSession = Depends(get_db),
):
    """Move deal to a new stage on the Kanban pipeline."""
    repo = DealRepository(db, current_user.organization_id)
    deal = await repo.get_by_id(deal_id)
    if not deal:
        raise NotFoundException("Deal not found.")
    old_status = deal.status
    updated = await repo.move_stage(deal, req)
    loaded = await repo.get_by_id(updated.id)

    from app.core.events import CRMEvent, CRMEventType, event_dispatcher
    from app.modules.deals.models import DealStatus

    await event_dispatcher.dispatch(
        CRMEvent(
            event_name=CRMEventType.DEAL_STAGE_CHANGED,
            organization_id=current_user.organization_id,
            entity_type="deal",
            entity_id=updated.id,
            actor_id=current_user.id,
            payload={"deal_id": updated.id, "stage_id": updated.stage_id, "status": updated.status},
        ),
        db,
    )

    if loaded and loaded.stage and "proposal" in loaded.stage.name.lower():
        await event_dispatcher.dispatch(
            CRMEvent(
                event_name=CRMEventType.PROPOSAL_SENT,
                organization_id=current_user.organization_id,
                entity_type="deal",
                entity_id=updated.id,
                actor_id=current_user.id,
                payload={"deal_id": updated.id, "stage_id": updated.stage_id, "title": updated.title},
            ),
            db,
        )

    if updated.status == DealStatus.WON.value and old_status != DealStatus.WON.value:
        await event_dispatcher.dispatch(
            CRMEvent(
                event_name=CRMEventType.DEAL_WON,
                organization_id=current_user.organization_id,
                entity_type="deal",
                entity_id=updated.id,
                actor_id=current_user.id,
                payload={"deal_id": updated.id, "title": updated.title, "value": updated.value},
            ),
            db,
        )

    return _to_deal_resp(loaded or updated)


@router.delete("/{deal_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_deal(
    deal_id: str,
    current_user: User = Depends(require_permission(Permission.DEALS_DELETE)),
    db: AsyncSession = Depends(get_db),
):
    """Delete a deal."""
    repo = DealRepository(db, current_user.organization_id)
    deal = await repo.get_by_id(deal_id)
    if not deal:
        raise NotFoundException("Deal not found.")
    await repo.delete(deal)
