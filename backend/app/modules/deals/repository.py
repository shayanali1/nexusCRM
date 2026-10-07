from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.modules.deals.models import Deal, DealStatus
from app.modules.deals.schemas import DealCreate, DealStageMoveRequest, DealUpdate
from app.modules.pipelines.models import PipelineStage


class DealRepository:
    def __init__(self, db: AsyncSession, organization_id: str):
        self.db = db
        self.org_id = organization_id

    async def list_all(
        self,
        pipeline_id: Optional[str] = None,
        stage_id: Optional[str] = None,
        status: Optional[str] = None,
        assigned_to_id: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 200,
        offset: int = 0,
    ) -> List[Deal]:
        stmt = (
            select(Deal)
            .where(Deal.organization_id == self.org_id)
            .options(
                selectinload(Deal.stage),
                selectinload(Deal.contact),
                selectinload(Deal.company),
                selectinload(Deal.assigned_to),
            )
            .order_by(Deal.created_at.desc())
        )
        if pipeline_id:
            stmt = stmt.where(Deal.pipeline_id == pipeline_id)
        if stage_id:
            stmt = stmt.where(Deal.stage_id == stage_id)
        if status:
            stmt = stmt.where(Deal.status == status.upper())
        if assigned_to_id:
            stmt = stmt.where(Deal.assigned_to_id == assigned_to_id)
        if search:
            search_pattern = f"%{search}%"
            stmt = stmt.where(Deal.title.ilike(search_pattern))

        stmt = stmt.offset(offset).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id(self, deal_id: str) -> Optional[Deal]:
        stmt = (
            select(Deal)
            .where(Deal.id == deal_id, Deal.organization_id == self.org_id)
            .options(
                selectinload(Deal.pipeline),
                selectinload(Deal.stage),
                selectinload(Deal.contact),
                selectinload(Deal.company),
                selectinload(Deal.assigned_to),
                selectinload(Deal.activities),
                selectinload(Deal.tasks),
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, data: DealCreate) -> Deal:
        deal = Deal(
            organization_id=self.org_id,
            pipeline_id=data.pipeline_id,
            stage_id=data.stage_id,
            contact_id=data.contact_id,
            company_id=data.company_id,
            assigned_to_id=data.assigned_to_id,
            title=data.title,
            value=data.value,
            currency=data.currency,
            status=data.status.value if hasattr(data.status, "value") else str(data.status),
            win_probability=data.win_probability,
            expected_close_date=data.expected_close_date,
            notes=data.notes,
            custom_fields=data.custom_fields,
        )
        self.db.add(deal)
        await self.db.commit()
        await self.db.refresh(deal)
        return deal

    async def update(self, deal: Deal, data: DealUpdate) -> Deal:
        for field, value in data.model_dump(exclude_unset=True).items():
            if hasattr(value, "value"):
                value = value.value
            setattr(deal, field, value)
        await self.db.commit()
        await self.db.refresh(deal)
        return deal

    async def move_stage(self, deal: Deal, req: DealStageMoveRequest) -> Deal:
        stage = (
            await self.db.execute(
                select(PipelineStage).where(
                    PipelineStage.id == req.stage_id,
                    PipelineStage.organization_id == self.org_id,
                )
            )
        ).scalar_one_or_none()

        deal.stage_id = req.stage_id
        if stage:
            deal.win_probability = req.win_probability if req.win_probability is not None else stage.win_probability
            if stage.is_won:
                deal.status = DealStatus.WON.value
                deal.closed_at = datetime.now(timezone.utc)
            elif stage.is_lost:
                deal.status = DealStatus.LOST.value
                deal.closed_at = datetime.now(timezone.utc)
                if req.lost_reason:
                    deal.lost_reason = req.lost_reason
            else:
                deal.status = DealStatus.OPEN.value
                deal.closed_at = None

        if req.status:
            deal.status = req.status.value if hasattr(req.status, "value") else str(req.status)

        await self.db.commit()
        await self.db.refresh(deal)
        return deal

    async def delete(self, deal: Deal) -> None:
        await self.db.delete(deal)
        await self.db.commit()
