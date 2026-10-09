from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.exceptions import NotFoundException
from app.core.permissions import Permission
from app.modules.auth.dependencies import get_current_user, require_permission
from app.modules.deals.models import Deal
from app.modules.deals.repository import DealRepository
from app.modules.deals.schemas import DealCreate, DealResponse, DealStageMoveRequest, DealUpdate
from app.modules.users.models import User

router = APIRouter(prefix="/deals", tags=["Deals"])


def _to_deal_resp(d: Deal) -> DealResponse:
    resp = DealResponse.model_validate(d)
    if d.stage:
        resp.stage_name = d.stage.name
    if d.contact:
        resp.contact_name = d.contact.full_name
    if d.company:
        resp.company_name = d.company.name
    if d.assigned_to:
        resp.assigned_to_name = d.assigned_to.full_name
    return resp


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
