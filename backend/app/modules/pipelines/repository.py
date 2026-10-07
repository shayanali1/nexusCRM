from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
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
        pipeline = Pipeline(
            organization_id=self.org_id,
            name=data.name,
            is_default=data.is_default,
        )
        self.db.add(pipeline)
        await self.db.flush()

        if data.stages:
            for s in data.stages:
                stage = PipelineStage(
                    organization_id=self.org_id,
                    pipeline_id=pipeline.id,
                    name=s.name,
                    order=s.order,
                    win_probability=s.win_probability,
                    is_won=s.is_won,
                    is_lost=s.is_lost,
                )
                self.db.add(stage)

        await self.db.commit()
        await self.db.refresh(pipeline)
        return pipeline

    async def add_stage(self, pipeline_id: str, data: PipelineStageCreate) -> PipelineStage:
        stage = PipelineStage(
            organization_id=self.org_id,
            pipeline_id=pipeline_id,
            name=data.name,
            order=data.order,
            win_probability=data.win_probability,
            is_won=data.is_won,
            is_lost=data.is_lost,
        )
        self.db.add(stage)
        await self.db.commit()
        await self.db.refresh(stage)
        return stage
