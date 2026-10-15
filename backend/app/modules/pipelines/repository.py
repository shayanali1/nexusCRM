from typing import List, Optional
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.core.exceptions import BadRequestException, NotFoundException
from app.modules.deals.models import Deal
from app.modules.pipelines.models import Pipeline, PipelineStage
from app.modules.pipelines.schemas import PipelineCreate, PipelineStageCreate, PipelineStageUpdate, PipelineUpdate


class PipelineRepository:
    def __init__(self, db: AsyncSession, organization_id: str):
        self.db = db
        self.org_id = organization_id

    async def list_all(self) -> List[Pipeline]:
        stmt = (
            select(Pipeline)
            .where(Pipeline.organization_id == self.org_id)
            .options(selectinload(Pipeline.stages))
            .order_by(Pipeline.is_default.desc(), Pipeline.name)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id(self, pipeline_id: str) -> Optional[Pipeline]:
        stmt = (
            select(Pipeline)
            .where(Pipeline.id == pipeline_id, Pipeline.organization_id == self.org_id)
            .options(selectinload(Pipeline.stages))
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, data: PipelineCreate) -> Pipeline:
        if data.is_default:
            # Unset any existing default pipeline in this organization
            await self.db.execute(
                update(Pipeline)
                .where(Pipeline.organization_id == self.org_id, Pipeline.is_default.is_(True))
                .values(is_default=False)
            )
            is_default = True
        else:
            existing_count = (await self.db.execute(
                select(func.count(Pipeline.id)).where(Pipeline.organization_id == self.org_id)
            )).scalar() or 0
            is_default = True if existing_count == 0 else False

        pipeline = Pipeline(
            organization_id=self.org_id,
            name=data.name,
            is_default=is_default,
        )
        self.db.add(pipeline)
        await self.db.flush()

        if data.stages:
            for idx, s in enumerate(data.stages):
                if s.is_won and s.is_lost:
                    raise BadRequestException("A stage cannot be marked as both won and lost.")
                stage = PipelineStage(
                    organization_id=self.org_id,
                    pipeline_id=pipeline.id,
                    name=s.name,
                    order=s.order if s.order else (idx + 1),
                    win_probability=s.win_probability,
                    is_won=s.is_won,
                    is_lost=s.is_lost,
                )
                self.db.add(stage)

        await self.db.commit()
        loaded = await self.get_by_id(pipeline.id)
        return loaded or pipeline

    async def update(self, pipeline: Pipeline, data: PipelineUpdate) -> Pipeline:
        update_dict = data.model_dump(exclude_unset=True)

        if "is_default" in update_dict:
            if update_dict["is_default"] is True:
                await self.db.execute(
                    update(Pipeline)
                    .where(
                        Pipeline.organization_id == self.org_id,
                        Pipeline.id != pipeline.id,
                        Pipeline.is_default.is_(True),
                    )
                    .values(is_default=False)
                )
                pipeline.is_default = True
            elif update_dict["is_default"] is False and pipeline.is_default is True:
                raise BadRequestException(
                    "Cannot unset the default sales pipeline. Set another pipeline as default instead."
                )

        if "name" in update_dict and update_dict["name"] is not None:
            pipeline.name = update_dict["name"]

        await self.db.commit()
        loaded = await self.get_by_id(pipeline.id)
        return loaded or pipeline

    async def delete(self, pipeline: Pipeline) -> None:
        if pipeline.is_default:
            raise BadRequestException("Cannot delete the default sales pipeline. Set another pipeline as default first.")

        deal_count = (await self.db.execute(
            select(func.count(Deal.id)).where(
                Deal.pipeline_id == pipeline.id,
                Deal.organization_id == self.org_id,
            )
        )).scalar() or 0
        if deal_count > 0:
            raise BadRequestException(f"Cannot delete pipeline containing {deal_count} active deal(s). Move or delete the deals first.")

        await self.db.delete(pipeline)
        await self.db.commit()

    async def get_stage_by_id(self, pipeline_id: str, stage_id: str) -> Optional[PipelineStage]:
        stmt = (
            select(PipelineStage)
            .where(
                PipelineStage.id == stage_id,
                PipelineStage.pipeline_id == pipeline_id,
                PipelineStage.organization_id == self.org_id,
            )
        )
        return (await self.db.execute(stmt)).scalars().first()

    async def add_stage(self, pipeline_id: str, data: PipelineStageCreate) -> PipelineStage:
        if data.is_won and data.is_lost:
            raise BadRequestException("A stage cannot be marked as both won and lost.")

        max_order = (await self.db.execute(
            select(func.coalesce(func.max(PipelineStage.order), 0)).where(
                PipelineStage.pipeline_id == pipeline_id,
                PipelineStage.organization_id == self.org_id,
            )
        )).scalar() or 0
        order = data.order if data.order and data.order > max_order else (max_order + 1)

        stage = PipelineStage(
            organization_id=self.org_id,
            pipeline_id=pipeline_id,
            name=data.name,
            order=order,
            win_probability=data.win_probability,
            is_won=data.is_won,
            is_lost=data.is_lost,
        )
        self.db.add(stage)
        await self.db.commit()
        await self.db.refresh(stage)
        return stage

    async def update_stage(self, stage: PipelineStage, data: PipelineStageUpdate) -> PipelineStage:
        update_dict = data.model_dump(exclude_unset=True)

        new_won = update_dict.get("is_won", stage.is_won)
        new_lost = update_dict.get("is_lost", stage.is_lost)
        if new_won and new_lost:
            raise BadRequestException("A stage cannot be marked as both won and lost.")

        for field, val in update_dict.items():
            setattr(stage, field, val)

        await self.db.commit()
        await self.db.refresh(stage)
        return stage

    async def delete_stage(self, stage: PipelineStage) -> None:
        deal_count = (await self.db.execute(
            select(func.count(Deal.id)).where(
                Deal.stage_id == stage.id,
                Deal.organization_id == self.org_id,
            )
        )).scalar() or 0
        if deal_count > 0:
            raise BadRequestException(f"Cannot delete pipeline stage containing {deal_count} active deal(s). Move the deals to another stage first.")

        stage_count = (await self.db.execute(
            select(func.count(PipelineStage.id)).where(
                PipelineStage.pipeline_id == stage.pipeline_id,
                PipelineStage.organization_id == self.org_id,
            )
        )).scalar() or 0
        if stage_count <= 1:
            raise BadRequestException("Cannot delete the only stage in a pipeline. A pipeline must have at least one stage.")

        await self.db.delete(stage)
        await self.db.commit()
