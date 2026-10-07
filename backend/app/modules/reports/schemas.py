from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class DashboardKPIs(BaseModel):
    total_leads: int
    new_leads_this_month: int
    open_deals_count: int
    pipeline_value: float
    won_revenue: float
    conversion_rate: float
    overdue_tasks_count: int
    tasks_due_today: int


class StageDistribution(BaseModel):
    stage_id: str
    stage_name: str
    order: int
    deal_count: int
    total_value: float
    win_probability: int


class SalesRepPerformance(BaseModel):
    user_id: str
    name: str
    deals_count: int
    won_deals_count: int
    total_revenue: float
    open_leads_count: int


class LeadSourceBreakdown(BaseModel):
    source: str
    count: int
    percentage: float


class DashboardOverviewResponse(BaseModel):
    kpis: DashboardKPIs
    stages: List[StageDistribution]
    reps: List[SalesRepPerformance]
    sources: List[LeadSourceBreakdown]
