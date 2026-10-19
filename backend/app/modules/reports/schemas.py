from datetime import datetime
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


class PipelineSummaryStage(BaseModel):
    stage_id: str
    stage_name: str
    order: int
    win_probability: int
    deal_count: int
    total_value: float
    weighted_value: float
    average_deal_value: float


class PipelineSummaryResponse(BaseModel):
    pipeline_id: str
    pipeline_name: str
    total_open_deals: int
    total_open_value: float
    weighted_forecast: float
    average_deal_value: float
    stages: List[PipelineSummaryStage]


class WonLostPerformanceResponse(BaseModel):
    pipeline_id: Optional[str] = None
    assigned_to_id: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    won_count: int
    lost_count: int
    closed_count: int
    won_value: float
    lost_value: float
    closed_value: float
    win_rate: float
    win_rate_percentage: float
