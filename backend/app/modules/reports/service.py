from datetime import datetime, timezone
from typing import Dict, List, Optional
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.core.exceptions import BadRequestException, NotFoundException
from app.modules.deals.models import Deal, DealStatus
from app.modules.leads.models import Lead, LeadStatus
from app.modules.pipelines.models import Pipeline, PipelineStage
from app.modules.reports.schemas import (
    DashboardKPIs,
    DashboardOverviewResponse,
    LeadSourceBreakdown,
    PipelineSummaryResponse,
    PipelineSummaryStage,
    SalesRepPerformance,
    StageDistribution,
    WonLostPerformanceResponse,
)
from app.modules.tasks.models import Task, TaskStatus
from app.modules.users.models import User


class ReportsService:
    def __init__(self, db: AsyncSession, organization_id: str):
        self.db = db
        self.org_id = organization_id

    async def get_dashboard_overview(self) -> DashboardOverviewResponse:
        now = datetime.now(timezone.utc)
        start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = now.replace(hour=23, minute=59, second=59, microsecond=999999)

        # 1. Query Leads
        lead_stmt = select(Lead).where(Lead.organization_id == self.org_id)
        leads = (await self.db.execute(lead_stmt)).scalars().all()

        total_leads = len(leads)
        new_leads_month = sum(1 for l in leads if l.created_at >= start_of_month)

        # Sources breakdown
        source_counts: Dict[str, int] = {}
        for l in leads:
            src = l.source or "Other"
            source_counts[src] = source_counts.get(src, 0) + 1

        sources_list: List[LeadSourceBreakdown] = []
        for src, cnt in sorted(source_counts.items(), key=lambda x: x[1], reverse=True):
            pct = (cnt / total_leads * 100) if total_leads > 0 else 0.0
            sources_list.append(LeadSourceBreakdown(source=src, count=cnt, percentage=round(pct, 1)))

        # 2. Query Deals
        deal_stmt = select(Deal).where(Deal.organization_id == self.org_id).options(selectinload(Deal.stage))
        deals = (await self.db.execute(deal_stmt)).scalars().all()

        open_deals = [d for d in deals if d.status == DealStatus.OPEN.value]
        won_deals = [d for d in deals if d.status == DealStatus.WON.value]

        pipeline_val = sum(d.value for d in open_deals)
        won_val = sum(d.value for d in won_deals)

        conversion_rate = 0.0
        if total_leads > 0:
            converted_leads = sum(1 for l in leads if l.status in [LeadStatus.WON.value, LeadStatus.QUALIFIED.value] or l.converted_at)
            conversion_rate = round((converted_leads / total_leads) * 100, 1)

        # 3. Query Stages
        stage_stmt = (
            select(PipelineStage)
            .join(Pipeline)
            .where(Pipeline.organization_id == self.org_id)
            .order_by(PipelineStage.order)
        )
        stages = (await self.db.execute(stage_stmt)).scalars().all()

        stage_dist: List[StageDistribution] = []
        for st in stages:
            matching_deals = [d for d in deals if d.stage_id == st.id]
            stage_dist.append(
                StageDistribution(
                    stage_id=st.id,
                    stage_name=st.name,
                    order=st.order,
                    deal_count=len(matching_deals),
                    total_value=sum(d.value for d in matching_deals),
                    win_probability=st.win_probability,
                )
            )

        # 4. Query Tasks
        task_stmt = select(Task).where(Task.organization_id == self.org_id)
        tasks = (await self.db.execute(task_stmt)).scalars().all()

        overdue_tasks = sum(1 for t in tasks if t.due_date < now and t.status in [TaskStatus.PENDING.value, TaskStatus.IN_PROGRESS.value])
        due_today = sum(1 for t in tasks if start_of_day <= t.due_date <= end_of_day and t.status != TaskStatus.COMPLETED.value)

        # 5. Sales Rep Leaderboard
        user_stmt = select(User).where(User.organization_id == self.org_id, User.is_active.is_(True))
        users = (await self.db.execute(user_stmt)).scalars().all()

        reps_list: List[SalesRepPerformance] = []
        for u in users:
            u_deals = [d for d in deals if d.assigned_to_id == u.id]
            u_won = [d for d in u_deals if d.status == DealStatus.WON.value]
            u_leads = [l for l in leads if l.assigned_to_id == u.id and l.status != LeadStatus.LOST.value]
            reps_list.append(
                SalesRepPerformance(
                    user_id=u.id,
                    name=u.full_name,
                    deals_count=len(u_deals),
                    won_deals_count=len(u_won),
                    total_revenue=sum(d.value for d in u_won),
                    open_leads_count=len(u_leads),
                )
            )

        kpis = DashboardKPIs(
            total_leads=total_leads,
            new_leads_this_month=new_leads_month,
            open_deals_count=len(open_deals),
            pipeline_value=round(pipeline_val, 2),
            won_revenue=round(won_val, 2),
            conversion_rate=conversion_rate,
            overdue_tasks_count=overdue_tasks,
            tasks_due_today=due_today,
        )

        return DashboardOverviewResponse(
            kpis=kpis,
            stages=stage_dist,
            reps=reps_list,
            sources=sources_list,
        )

    async def get_pipeline_summary(
        self,
        pipeline_id: Optional[str] = None,
        assigned_to_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> PipelineSummaryResponse:
        """Provide organization-scoped pipeline metrics and weighted forecasts."""
        if start_date and end_date and start_date > end_date:
            raise BadRequestException("Start date cannot be after end date.")

        if pipeline_id:
            pipe_stmt = select(Pipeline).where(
                Pipeline.id == pipeline_id,
                Pipeline.organization_id == self.org_id,
            )
            pipeline = (await self.db.execute(pipe_stmt)).scalars().first()
            if not pipeline:
                raise NotFoundException("Pipeline not found.")
        else:
            def_stmt = select(Pipeline).where(
                Pipeline.organization_id == self.org_id,
                Pipeline.is_default.is_(True),
            )
            pipeline = (await self.db.execute(def_stmt)).scalars().first()
            if not pipeline:
                first_stmt = (
                    select(Pipeline)
                    .where(Pipeline.organization_id == self.org_id)
                    .order_by(Pipeline.created_at.asc())
                )
                pipeline = (await self.db.execute(first_stmt)).scalars().first()
                if not pipeline:
                    raise NotFoundException("Pipeline not found.")

        stages_stmt = (
            select(PipelineStage)
            .where(
                PipelineStage.pipeline_id == pipeline.id,
                PipelineStage.organization_id == self.org_id,
            )
            .order_by(PipelineStage.order.asc())
        )
        stages = (await self.db.execute(stages_stmt)).scalars().all()

        stmt = (
            select(
                Deal.stage_id,
                func.count(Deal.id).label("deal_count"),
                func.coalesce(func.sum(Deal.value), 0.0).label("total_value"),
            )
            .where(
                Deal.organization_id == self.org_id,
                Deal.pipeline_id == pipeline.id,
                Deal.status == DealStatus.OPEN.value,
            )
        )
        if assigned_to_id:
            stmt = stmt.where(Deal.assigned_to_id == assigned_to_id)
        if start_date:
            stmt = stmt.where(func.coalesce(Deal.expected_close_date, Deal.created_at) >= start_date)
        if end_date:
            stmt = stmt.where(func.coalesce(Deal.expected_close_date, Deal.created_at) <= end_date)
        stmt = stmt.group_by(Deal.stage_id)

        rows = (await self.db.execute(stmt)).all()
        stage_map = {row.stage_id: (row.deal_count, float(row.total_value)) for row in rows}

        stage_summaries: List[PipelineSummaryStage] = []
        for stage in stages:
            count, val = stage_map.get(stage.id, (0, 0.0))
            val = round(val, 2)
            prob = stage.win_probability or 0
            weighted_val = round(val * (prob / 100.0), 2)
            avg_val = round(val / count, 2) if count > 0 else 0.0

            stage_summaries.append(
                PipelineSummaryStage(
                    stage_id=stage.id,
                    stage_name=stage.name,
                    order=stage.order,
                    win_probability=prob,
                    deal_count=count,
                    total_value=val,
                    weighted_value=weighted_val,
                    average_deal_value=avg_val,
                )
            )

        total_open_deals = sum(s.deal_count for s in stage_summaries)
        total_open_value = round(sum(s.total_value for s in stage_summaries), 2)
        weighted_forecast = round(sum(s.weighted_value for s in stage_summaries), 2)
        average_deal_value = round(total_open_value / total_open_deals, 2) if total_open_deals > 0 else 0.0

        return PipelineSummaryResponse(
            pipeline_id=pipeline.id,
            pipeline_name=pipeline.name,
            total_open_deals=total_open_deals,
            total_open_value=total_open_value,
            weighted_forecast=weighted_forecast,
            average_deal_value=average_deal_value,
            stages=stage_summaries,
        )

    async def get_won_lost_performance(
        self,
        pipeline_id: Optional[str] = None,
        assigned_to_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> WonLostPerformanceResponse:
        """Provide win/loss performance and win rate for closed deals in requested date range."""
        if start_date and end_date and start_date > end_date:
            raise BadRequestException("Start date cannot be after end date.")

        if pipeline_id:
            pipe_stmt = select(Pipeline.id).where(
                Pipeline.id == pipeline_id,
                Pipeline.organization_id == self.org_id,
            )
            pipe = (await self.db.execute(pipe_stmt)).scalar_one_or_none()
            if not pipe:
                raise NotFoundException("Pipeline not found.")

        closed_date_col = func.coalesce(Deal.closed_at, Deal.updated_at)
        stmt = (
            select(
                Deal.status,
                func.count(Deal.id).label("count"),
                func.coalesce(func.sum(Deal.value), 0.0).label("total_value"),
            )
            .where(
                Deal.organization_id == self.org_id,
                Deal.status.in_([DealStatus.WON.value, DealStatus.LOST.value]),
            )
        )
        if pipeline_id:
            stmt = stmt.where(Deal.pipeline_id == pipeline_id)
        if assigned_to_id:
            stmt = stmt.where(Deal.assigned_to_id == assigned_to_id)
        if start_date:
            stmt = stmt.where(closed_date_col >= start_date)
        if end_date:
            stmt = stmt.where(closed_date_col <= end_date)
        stmt = stmt.group_by(Deal.status)

        rows = (await self.db.execute(stmt)).all()
        status_counts = {DealStatus.WON.value: 0, DealStatus.LOST.value: 0}
        status_values = {DealStatus.WON.value: 0.0, DealStatus.LOST.value: 0.0}

        for row in rows:
            st = row.status
            if st in status_counts:
                status_counts[st] = row.count
                status_values[st] = float(row.total_value)

        won_count = status_counts[DealStatus.WON.value]
        lost_count = status_counts[DealStatus.LOST.value]
        closed_count = won_count + lost_count
        won_value = round(status_values[DealStatus.WON.value], 2)
        lost_value = round(status_values[DealStatus.LOST.value], 2)
        closed_value = round(won_value + lost_value, 2)

        if closed_count > 0:
            win_rate = round(won_count / closed_count, 4)
            win_rate_percentage = round(win_rate * 100.0, 2)
        else:
            win_rate = 0.0
            win_rate_percentage = 0.0

        return WonLostPerformanceResponse(
            pipeline_id=pipeline_id,
            assigned_to_id=assigned_to_id,
            start_date=start_date,
            end_date=end_date,
            won_count=won_count,
            lost_count=lost_count,
            closed_count=closed_count,
            won_value=won_value,
            lost_value=lost_value,
            closed_value=closed_value,
            win_rate=win_rate,
            win_rate_percentage=win_rate_percentage,
        )
