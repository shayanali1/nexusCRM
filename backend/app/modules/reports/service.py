from datetime import datetime, timezone
from typing import Dict, List
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.modules.deals.models import Deal, DealStatus
from app.modules.leads.models import Lead, LeadStatus
from app.modules.pipelines.models import Pipeline, PipelineStage
from app.modules.reports.schemas import (
    DashboardKPIs,
    DashboardOverviewResponse,
    LeadSourceBreakdown,
    SalesRepPerformance,
    StageDistribution,
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
