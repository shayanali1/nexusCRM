from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.core.exceptions import BadRequestException, NotFoundException
from app.modules.companies.models import Company
from app.modules.contacts.models import Contact
from app.modules.deals.models import Deal, DealStatus
from app.modules.deals.schemas import DealCreate, DealStageMoveRequest, DealUpdate
from app.modules.pipelines.models import Pipeline, PipelineStage
from app.modules.users.models import User


DEALS_SORT_FIELDS = {
    "title": Deal.title,
    "value": Deal.value,
    "status": Deal.status,
    "created_at": Deal.created_at,
    "updated_at": Deal.updated_at,
    "expected_close_date": Deal.expected_close_date,
}


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
        limit: int = 100,
        offset: int = 0,
        contact_id: Optional[str] = None,
        company_id: Optional[str] = None,
        sort_by: Optional[str] = None,
        sort_order: Optional[str] = None,
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
        )
        if pipeline_id and pipeline_id.strip():
            stmt = stmt.where(Deal.pipeline_id == pipeline_id.strip())
        if stage_id and stage_id.strip():
            stmt = stmt.where(Deal.stage_id == stage_id.strip())
        if status and status.strip():
            clean_status = status.strip().upper()
            if clean_status not in ("OPEN", "WON", "LOST"):
                raise BadRequestException("Invalid deal status. Must be one of: OPEN, WON, LOST.")
            stmt = stmt.where(Deal.status == clean_status)
        if assigned_to_id and assigned_to_id.strip():
            stmt = stmt.where(Deal.assigned_to_id == assigned_to_id.strip())
        if contact_id and contact_id.strip():
            stmt = stmt.where(Deal.contact_id == contact_id.strip())
        if company_id and company_id.strip():
            stmt = stmt.where(Deal.company_id == company_id.strip())
        if search and search.strip():
            search_pattern = f"%{search.strip()}%"
            stmt = stmt.where(Deal.title.ilike(search_pattern))

        clean_sort_by = sort_by.strip().lower() if sort_by and sort_by.strip() else None
        clean_sort_order = sort_order.strip().lower() if sort_order and sort_order.strip() else None

        if clean_sort_order is not None and clean_sort_order not in ("asc", "desc"):
            raise BadRequestException("Invalid sort order. Must be 'asc' or 'desc'.")

        if clean_sort_by is not None:
            if clean_sort_by not in DEALS_SORT_FIELDS:
                allowed = ", ".join(sorted(DEALS_SORT_FIELDS.keys()))
                raise BadRequestException(f"Invalid sort field '{clean_sort_by}'. Allowed fields: {allowed}")

            direction = clean_sort_order if clean_sort_order else ("desc" if clean_sort_by in ("created_at", "updated_at") else "asc")
            col = DEALS_SORT_FIELDS[clean_sort_by]
            stmt = stmt.order_by(col.desc() if direction == "desc" else col.asc(), Deal.id.asc())
        elif clean_sort_order is not None:
            if clean_sort_order == "desc":
                stmt = stmt.order_by(Deal.created_at.desc(), Deal.id.asc())
            else:
                stmt = stmt.order_by(Deal.created_at.asc(), Deal.id.asc())
        else:
            stmt = stmt.order_by(Deal.created_at.desc(), Deal.id.asc())

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

    async def _validate_relationships(
        self,
        pipeline_id: Optional[str] = None,
        stage_id: Optional[str] = None,
        contact_id: Optional[str] = None,
        company_id: Optional[str] = None,
        assigned_to_id: Optional[str] = None,
        validate_pipeline_and_stage: bool = False,
    ) -> None:
        if validate_pipeline_and_stage:
            if pipeline_id:
                p_stmt = select(Pipeline.id).where(
                    Pipeline.id == pipeline_id,
                    Pipeline.organization_id == self.org_id,
                )
                if not (await self.db.execute(p_stmt)).scalar_one_or_none():
                    raise NotFoundException("Pipeline not found.")

            if stage_id:
                s_stmt = select(PipelineStage).where(
                    PipelineStage.id == stage_id,
                    PipelineStage.organization_id == self.org_id,
                )
                stage = (await self.db.execute(s_stmt)).scalars().first()
                if not stage:
                    raise NotFoundException("Pipeline stage not found.")
                if pipeline_id and stage.pipeline_id != pipeline_id:
                    raise BadRequestException("Pipeline stage does not belong to the selected pipeline.")

        if contact_id:
            ct_stmt = select(Contact.id).where(
                Contact.id == contact_id,
                Contact.organization_id == self.org_id,
            )
            if not (await self.db.execute(ct_stmt)).scalar_one_or_none():
                raise NotFoundException("Contact not found.")

        if company_id:
            c_stmt = select(Company.id).where(
                Company.id == company_id,
                Company.organization_id == self.org_id,
            )
            if not (await self.db.execute(c_stmt)).scalar_one_or_none():
                raise NotFoundException("Company not found.")

        if assigned_to_id:
            u_stmt = select(User.id).where(
                User.id == assigned_to_id,
                User.organization_id == self.org_id,
                User.is_active.is_(True),
            )
            if not (await self.db.execute(u_stmt)).scalar_one_or_none():
                raise NotFoundException("User not found.")

    async def create(self, data: DealCreate) -> Deal:
        await self._validate_relationships(
            pipeline_id=data.pipeline_id,
            stage_id=data.stage_id,
            contact_id=data.contact_id,
            company_id=data.company_id,
            assigned_to_id=data.assigned_to_id,
            validate_pipeline_and_stage=True,
        )
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
        update_dict = data.model_dump(exclude_unset=True)

        target_pipeline_id = update_dict.get("pipeline_id", deal.pipeline_id)
        target_stage_id = update_dict.get("stage_id", deal.stage_id)
        validate_pipe_stage = "pipeline_id" in update_dict or "stage_id" in update_dict

        await self._validate_relationships(
            pipeline_id=target_pipeline_id if validate_pipe_stage else None,
            stage_id=target_stage_id if validate_pipe_stage else None,
            contact_id=update_dict.get("contact_id") if "contact_id" in update_dict else None,
            company_id=update_dict.get("company_id") if "company_id" in update_dict else None,
            assigned_to_id=update_dict.get("assigned_to_id") if "assigned_to_id" in update_dict else None,
            validate_pipeline_and_stage=validate_pipe_stage,
        )

        status_in_req = "status" in update_dict
        req_status = None
        if status_in_req:
            val = update_dict["status"]
            req_status = val.value if hasattr(val, "value") else str(val)

        previous_status = str(deal.status)
        resulting_status = req_status if status_in_req else previous_status

        # Enforce lifecycle status, timestamp, and stage consistency
        if validate_pipe_stage or status_in_req:
            stage_obj = (
                await self.db.execute(
                    select(PipelineStage).where(
                        PipelineStage.id == target_stage_id,
                        PipelineStage.organization_id == self.org_id,
                    )
                )
            ).scalars().first()
            if stage_obj:
                if stage_obj.is_won:
                    if status_in_req and req_status != DealStatus.WON.value:
                        raise BadRequestException("Cannot assign a non-WON status to a deal on a won stage.")
                    resulting_status = DealStatus.WON.value
                elif stage_obj.is_lost:
                    if status_in_req and req_status != DealStatus.LOST.value:
                        raise BadRequestException("Cannot assign a non-LOST status to a deal on a lost stage.")
                    resulting_status = DealStatus.LOST.value
                else:
                    if status_in_req and req_status != DealStatus.OPEN.value:
                        raise BadRequestException("Cannot assign a non-OPEN status to a deal on an open stage.")
                    if previous_status in (DealStatus.WON.value, DealStatus.LOST.value) or status_in_req:
                        resulting_status = DealStatus.OPEN.value

        for field, value in update_dict.items():
            if field in ("pipeline_id", "stage_id", "status"):
                continue
            if hasattr(value, "value"):
                value = value.value
            setattr(deal, field, value)

        deal.pipeline_id = target_pipeline_id
        deal.stage_id = target_stage_id
        deal.status = resulting_status

        if deal.status == DealStatus.WON.value:
            if not deal.closed_at or previous_status != DealStatus.WON.value:
                deal.closed_at = datetime.now(timezone.utc)
            deal.lost_reason = None
        elif deal.status == DealStatus.LOST.value:
            if not deal.closed_at or previous_status != DealStatus.LOST.value:
                deal.closed_at = datetime.now(timezone.utc)
            if "lost_reason" in update_dict:
                deal.lost_reason = update_dict["lost_reason"]
        elif deal.status == DealStatus.OPEN.value:
            deal.closed_at = None
            deal.lost_reason = None

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
        ).scalars().first()
        if not stage:
            raise NotFoundException("Pipeline stage not found.")
        if stage.pipeline_id != deal.pipeline_id:
            raise BadRequestException("Pipeline stage does not belong to the selected pipeline.")

        deal.stage_id = req.stage_id
        deal.win_probability = req.win_probability if req.win_probability is not None else stage.win_probability

        if req.status:
            status_val = req.status.value if hasattr(req.status, "value") else str(req.status)
            if stage.is_won and status_val != DealStatus.WON.value:
                raise BadRequestException("Cannot assign a non-WON status when moving to a won stage.")
            if stage.is_lost and status_val != DealStatus.LOST.value:
                raise BadRequestException("Cannot assign a non-LOST status when moving to a lost stage.")
            if not stage.is_won and not stage.is_lost and status_val != DealStatus.OPEN.value:
                raise BadRequestException("Cannot assign a non-OPEN status when moving to an open stage.")
            deal.status = status_val
        elif stage.is_won:
            deal.status = DealStatus.WON.value
        elif stage.is_lost:
            deal.status = DealStatus.LOST.value
        else:
            deal.status = DealStatus.OPEN.value

        if deal.status == DealStatus.WON.value:
            deal.closed_at = datetime.now(timezone.utc)
            deal.lost_reason = None
        elif deal.status == DealStatus.LOST.value:
            deal.closed_at = datetime.now(timezone.utc)
            if req.lost_reason:
                deal.lost_reason = req.lost_reason
        elif deal.status == DealStatus.OPEN.value:
            deal.closed_at = None
            deal.lost_reason = None

        await self.db.commit()
        await self.db.refresh(deal)
        return deal

    async def delete(self, deal: Deal) -> None:
        await self.db.delete(deal)
        await self.db.commit()
