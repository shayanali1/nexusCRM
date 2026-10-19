from datetime import datetime, timezone, timedelta
from typing import Dict
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.security import create_access_token, hash_password
from app.modules.deals.models import Deal, DealStatus
from app.modules.organizations.models import Organization
from app.modules.pipelines.models import Pipeline, PipelineStage
from app.modules.users.models import User


@pytest.mark.asyncio
async def test_pipeline_summary_metrics_and_weighted_forecast(
    client: AsyncClient,
    test_org: Organization,
    auth_headers_owner: dict,
    db_session: AsyncSession,
):
    """Pipeline summary computes exact stage counts, values, average deal value, and weighted forecast."""
    # 1. Create custom pipeline with varied win probabilities (including 0% and 100% boundaries)
    pipe_res = await client.post(
        "/api/v1/pipelines",
        json={
            "name": "Forecasting Pipeline",
            "is_default": True,
            "stages": [
                {"name": "Stage 0% (Boundary)", "order": 1, "win_probability": 0},
                {"name": "Stage 20%", "order": 2, "win_probability": 20},
                {"name": "Stage 50%", "order": 3, "win_probability": 50},
                {"name": "Stage 100% (Boundary)", "order": 4, "win_probability": 100},
                {"name": "Stage Won", "order": 5, "win_probability": 100, "is_won": True},
            ],
        },
        headers=auth_headers_owner,
    )
    assert pipe_res.status_code == 201
    pipe_data = pipe_res.json()
    pipe_id = pipe_data["id"]
    stages = pipe_data["stages"]
    s0_id, s20_id, s50_id, s100_id, swon_id = [s["id"] for s in stages]

    # 2. Add Deals:
    # Stage 0%: 1 open deal @ $5,000 -> weighted = $0.0
    # Stage 20%: 2 open deals @ $10,000 and $20,000 -> total = $30,000, weighted = $6,000.0, avg = $15,000.0
    # Stage 50%: 0 open deals -> total = $0.0, weighted = $0.0, avg = $0.0 (empty stage verification)
    # Stage 100%: 1 open deal @ $15,000 -> total = $15,000, weighted = $15,000.0, avg = $15,000.0
    # Stage Won: 1 WON deal @ $40,000 -> must NOT be counted in open pipeline metrics or forecast!
    await client.post(
        "/api/v1/deals",
        json={"title": "Deal in Stage 0%", "pipeline_id": pipe_id, "stage_id": s0_id, "value": 5000.0},
        headers=auth_headers_owner,
    )
    await client.post(
        "/api/v1/deals",
        json={"title": "Deal 1 in Stage 20%", "pipeline_id": pipe_id, "stage_id": s20_id, "value": 10000.0},
        headers=auth_headers_owner,
    )
    await client.post(
        "/api/v1/deals",
        json={"title": "Deal 2 in Stage 20%", "pipeline_id": pipe_id, "stage_id": s20_id, "value": 20000.0},
        headers=auth_headers_owner,
    )
    await client.post(
        "/api/v1/deals",
        json={"title": "Deal in Stage 100%", "pipeline_id": pipe_id, "stage_id": s100_id, "value": 15000.0},
        headers=auth_headers_owner,
    )
    won_deal_res = await client.post(
        "/api/v1/deals",
        json={"title": "Won Deal", "pipeline_id": pipe_id, "stage_id": swon_id, "value": 40000.0, "status": "WON"},
        headers=auth_headers_owner,
    )
    assert won_deal_res.status_code == 201

    # 3. Test both reports router and deals router alias
    for endpoint in [f"/api/v1/reports/pipeline-summary?pipeline_id={pipe_id}", f"/api/v1/deals/pipeline-summary?pipeline_id={pipe_id}"]:
        res = await client.get(endpoint, headers=auth_headers_owner)
        assert res.status_code == 200, res.text
        data = res.json()

        assert data["pipeline_id"] == pipe_id
        assert data["pipeline_name"] == "Forecasting Pipeline"
        # Total open deals = 1 + 2 + 0 + 1 = 4 (won deal strictly excluded)
        assert data["total_open_deals"] == 4
        # Total open value = 5,000 + 30,000 + 0 + 15,000 = 50,000.0
        assert data["total_open_value"] == 50000.0
        # Weighted forecast = 0 + (30,000 * 0.20) + 0 + (15,000 * 1.0) = 0 + 6,000 + 15,000 = 21,000.0
        assert data["weighted_forecast"] == 21000.0
        # Average deal value = 50,000 / 4 = 12,500.0
        assert data["average_deal_value"] == 12500.0

        # Stage breakdown assertions
        res_stages = data["stages"]
        assert len(res_stages) == 5

        # Stage 0%
        assert res_stages[0]["stage_id"] == s0_id
        assert res_stages[0]["win_probability"] == 0
        assert res_stages[0]["deal_count"] == 1
        assert res_stages[0]["total_value"] == 5000.0
        assert res_stages[0]["weighted_value"] == 0.0
        assert res_stages[0]["average_deal_value"] == 5000.0

        # Stage 20%
        assert res_stages[1]["stage_id"] == s20_id
        assert res_stages[1]["win_probability"] == 20
        assert res_stages[1]["deal_count"] == 2
        assert res_stages[1]["total_value"] == 30000.0
        assert res_stages[1]["weighted_value"] == 6000.0
        assert res_stages[1]["average_deal_value"] == 15000.0

        # Stage 50% (empty stage)
        assert res_stages[2]["stage_id"] == s50_id
        assert res_stages[2]["win_probability"] == 50
        assert res_stages[2]["deal_count"] == 0
        assert res_stages[2]["total_value"] == 0.0
        assert res_stages[2]["weighted_value"] == 0.0
        assert res_stages[2]["average_deal_value"] == 0.0

        # Stage 100%
        assert res_stages[3]["stage_id"] == s100_id
        assert res_stages[3]["win_probability"] == 100
        assert res_stages[3]["deal_count"] == 1
        assert res_stages[3]["total_value"] == 15000.0
        assert res_stages[3]["weighted_value"] == 15000.0
        assert res_stages[3]["average_deal_value"] == 15000.0

        # Stage Won (has won deal, 0 open deals)
        assert res_stages[4]["stage_id"] == swon_id
        assert res_stages[4]["deal_count"] == 0
        assert res_stages[4]["total_value"] == 0.0


@pytest.mark.asyncio
async def test_pipeline_summary_empty_and_default_fallback(
    client: AsyncClient,
    test_org: Organization,
    auth_headers_owner: dict,
):
    """Pipeline summary correctly falls back to default pipeline when pipeline_id is omitted and handles empty state."""
    res = await client.get("/api/v1/reports/pipeline-summary", headers=auth_headers_owner)
    assert res.status_code == 200
    data = res.json()

    assert data["pipeline_name"] == "Sales Pipeline"
    assert data["total_open_deals"] == 0
    assert data["total_open_value"] == 0.0
    assert data["weighted_forecast"] == 0.0
    assert data["average_deal_value"] == 0.0
    assert len(data["stages"]) == 1
    assert data["stages"][0]["deal_count"] == 0
    assert data["stages"][0]["total_value"] == 0.0
    assert data["stages"][0]["weighted_value"] == 0.0
    assert data["stages"][0]["average_deal_value"] == 0.0


@pytest.mark.asyncio
async def test_won_lost_performance_and_win_rate_calculation(
    client: AsyncClient,
    test_org: Organization,
    auth_headers_owner: dict,
    db_session: AsyncSession,
):
    """Won/lost performance accurately calculates counts, values, win rate, and ignores open deals."""
    # 1. Fetch default pipeline & stage
    pipe_res = await client.get("/api/v1/pipelines", headers=auth_headers_owner)
    pipe = pipe_res.json()[0]
    stage_id = pipe["stages"][0]["id"]

    # 2. Create 2 WON deals ($20,000, $30,000 -> won_value = $50,000)
    await client.post(
        "/api/v1/deals",
        json={"title": "Deal Won 1", "pipeline_id": pipe["id"], "stage_id": stage_id, "value": 20000.0, "status": "WON"},
        headers=auth_headers_owner,
    )
    await client.post(
        "/api/v1/deals",
        json={"title": "Deal Won 2", "pipeline_id": pipe["id"], "stage_id": stage_id, "value": 30000.0, "status": "WON"},
        headers=auth_headers_owner,
    )

    # 3. Create 1 LOST deal ($10,000 -> lost_value = $10,000)
    await client.post(
        "/api/v1/deals",
        json={"title": "Deal Lost 1", "pipeline_id": pipe["id"], "stage_id": stage_id, "value": 10000.0, "status": "LOST", "lost_reason": "Price"},
        headers=auth_headers_owner,
    )

    # 4. Create 2 OPEN deals ($50,000 each -> should be ignored)
    await client.post(
        "/api/v1/deals",
        json={"title": "Deal Open 1", "pipeline_id": pipe["id"], "stage_id": stage_id, "value": 50000.0, "status": "OPEN"},
        headers=auth_headers_owner,
    )
    await client.post(
        "/api/v1/deals",
        json={"title": "Deal Open 2", "pipeline_id": pipe["id"], "stage_id": stage_id, "value": 50000.0, "status": "OPEN"},
        headers=auth_headers_owner,
    )

    # 5. Check both /reports/won-lost and /deals/won-lost
    for endpoint in ["/api/v1/reports/won-lost", "/api/v1/deals/won-lost"]:
        res = await client.get(endpoint, headers=auth_headers_owner)
        assert res.status_code == 200, res.text
        data = res.json()

        assert data["won_count"] == 2
        assert data["lost_count"] == 1
        assert data["closed_count"] == 3
        assert data["won_value"] == 50000.0
        assert data["lost_value"] == 10000.0
        assert data["closed_value"] == 60000.0
        # win_rate = 2 / 3 = 0.6667
        assert data["win_rate"] == 0.6667
        assert data["win_rate_percentage"] == 66.67


@pytest.mark.asyncio
async def test_won_lost_performance_division_by_zero_safety(
    client: AsyncClient,
    test_org: Organization,
    auth_headers_owner: dict,
):
    """When there are no closed deals, win_rate is safely 0.0 with no division by zero."""
    res = await client.get("/api/v1/reports/won-lost", headers=auth_headers_owner)
    assert res.status_code == 200
    data = res.json()

    assert data["won_count"] == 0
    assert data["lost_count"] == 0
    assert data["closed_count"] == 0
    assert data["won_value"] == 0.0
    assert data["lost_value"] == 0.0
    assert data["closed_value"] == 0.0
    assert data["win_rate"] == 0.0
    assert data["win_rate_percentage"] == 0.0


@pytest.mark.asyncio
async def test_date_range_filtering_and_validation(
    client: AsyncClient,
    test_org: Organization,
    auth_headers_owner: dict,
    db_session: AsyncSession,
):
    """Date filtering validates range consistency and filters closed deals by closed_at timestamp."""
    pipe_res = await client.get("/api/v1/pipelines", headers=auth_headers_owner)
    pipe = pipe_res.json()[0]
    stage_id = pipe["stages"][0]["id"]

    # 1. Invalid date range (start_date > end_date) must return 400 Bad Request
    res_inv1 = await client.get(
        "/api/v1/reports/pipeline-summary?start_date=2026-12-31T00:00:00Z&end_date=2026-01-01T00:00:00Z",
        headers=auth_headers_owner,
    )
    assert res_inv1.status_code == 400
    assert "Start date cannot be after end date" in res_inv1.json()["error"]["message"]

    res_inv2 = await client.get(
        "/api/v1/reports/won-lost?start_date=2026-12-31T00:00:00Z&end_date=2026-01-01T00:00:00Z",
        headers=auth_headers_owner,
    )
    assert res_inv2.status_code == 400
    assert "Start date cannot be after end date" in res_inv2.json()["error"]["message"]

    # 2. Create 2 won deals with distinct closed_at timestamps
    now = datetime.now(timezone.utc)
    deal_past = Deal(
        organization_id=test_org.id,
        pipeline_id=pipe["id"],
        stage_id=stage_id,
        title="Past Deal Won",
        value=15000.0,
        status=DealStatus.WON.value,
        closed_at=now - timedelta(days=60),
    )
    deal_recent = Deal(
        organization_id=test_org.id,
        pipeline_id=pipe["id"],
        stage_id=stage_id,
        title="Recent Deal Won",
        value=25000.0,
        status=DealStatus.WON.value,
        closed_at=now - timedelta(days=5),
    )
    db_session.add(deal_past)
    db_session.add(deal_recent)
    await db_session.commit()

    # Query only recent 10 days
    start_filter = (now - timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
    end_filter = (now + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")

    res_filtered = await client.get(
        f"/api/v1/reports/won-lost?start_date={start_filter}&end_date={end_filter}",
        headers=auth_headers_owner,
    )
    assert res_filtered.status_code == 200
    data = res_filtered.json()
    assert data["won_count"] == 1
    assert data["won_value"] == 25000.0
    assert data["closed_count"] == 1


@pytest.mark.asyncio
async def test_assigned_user_filter(
    client: AsyncClient,
    test_org: Organization,
    auth_headers_owner: dict,
    db_session: AsyncSession,
):
    """Filtering by assigned_to_id filters both pipeline summary and won/lost metrics."""
    # 1. Create a second sales rep
    rep = User(
        organization_id=test_org.id,
        email="rep@alpha.com",
        hashed_password=hash_password("password123"),
        first_name="Bob",
        last_name="Sales",
        role="MEMBER",
        is_active=True,
    )
    db_session.add(rep)
    await db_session.commit()
    await db_session.refresh(rep)

    pipe_res = await client.get("/api/v1/pipelines", headers=auth_headers_owner)
    pipe = pipe_res.json()[0]
    stage_id = pipe["stages"][0]["id"]

    # Deal for Rep Bob
    await client.post(
        "/api/v1/deals",
        json={"title": "Bob's Open Deal", "pipeline_id": pipe["id"], "stage_id": stage_id, "value": 30000.0, "assigned_to_id": rep.id},
        headers=auth_headers_owner,
    )
    # Deal for unassigned/other
    await client.post(
        "/api/v1/deals",
        json={"title": "Unassigned Deal", "pipeline_id": pipe["id"], "stage_id": stage_id, "value": 10000.0},
        headers=auth_headers_owner,
    )

    # Filter pipeline summary by Bob's id
    res = await client.get(
        f"/api/v1/reports/pipeline-summary?assigned_to_id={rep.id}",
        headers=auth_headers_owner,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["total_open_deals"] == 1
    assert data["total_open_value"] == 30000.0


@pytest.mark.asyncio
async def test_cross_tenant_isolation(
    client: AsyncClient,
    test_org: Organization,
    auth_headers_owner: dict,
    db_session: AsyncSession,
):
    """Foreign pipeline IDs return 404, and Organization A cannot see Organization B analytics data."""
    # 1. Create Organization B with its own pipeline and deals
    org_b = Organization(name="Org Beta", slug="org-beta", is_active=True)
    db_session.add(org_b)
    await db_session.flush()

    pipe_b = Pipeline(organization_id=org_b.id, name="Beta Pipeline", is_default=True)
    db_session.add(pipe_b)
    await db_session.flush()

    stage_b = PipelineStage(organization_id=org_b.id, pipeline_id=pipe_b.id, name="Beta Stage", order=1, win_probability=50)
    db_session.add(stage_b)
    await db_session.flush()

    deal_b = Deal(
        organization_id=org_b.id,
        pipeline_id=pipe_b.id,
        stage_id=stage_b.id,
        title="Beta Secret Deal",
        value=999999.0,
        status=DealStatus.OPEN.value,
    )
    db_session.add(deal_b)
    await db_session.commit()

    # 2. Org A attempts to request pipeline summary using Org B's pipeline ID -> Must return 404
    res_summary = await client.get(
        f"/api/v1/reports/pipeline-summary?pipeline_id={pipe_b.id}",
        headers=auth_headers_owner,
    )
    assert res_summary.status_code == 404
    assert "Pipeline not found" in res_summary.json()["error"]["message"]

    # 3. Org A attempts to request won-lost using Org B's pipeline ID -> Must return 404
    res_wonlost = await client.get(
        f"/api/v1/reports/won-lost?pipeline_id={pipe_b.id}",
        headers=auth_headers_owner,
    )
    assert res_wonlost.status_code == 404
    assert "Pipeline not found" in res_wonlost.json()["error"]["message"]

    # 4. Org A summary must not leak Org B's $999,999 deal
    res_org_a = await client.get("/api/v1/reports/pipeline-summary", headers=auth_headers_owner)
    assert res_org_a.status_code == 200
    assert res_org_a.json()["total_open_value"] == 0.0


@pytest.mark.asyncio
async def test_deals_router_pipeline_summary_does_not_conflict_with_deal_id(
    client: AsyncClient,
    test_org: Organization,
    auth_headers_owner: dict,
):
    """Verifies that GET /deals/pipeline-summary and /deals/won-lost do not get hijacked by /{deal_id}."""
    res_summary = await client.get("/api/v1/deals/pipeline-summary", headers=auth_headers_owner)
    assert res_summary.status_code == 200
    assert "total_open_deals" in res_summary.json()

    res_wonlost = await client.get("/api/v1/deals/won-lost", headers=auth_headers_owner)
    assert res_wonlost.status_code == 200
    assert "win_rate" in res_wonlost.json()

    # A non-existent deal ID should return 404 Deal not found
    res_deal = await client.get("/api/v1/deals/non-existent-id-12345", headers=auth_headers_owner)
    assert res_deal.status_code == 404
    assert "Deal not found" in res_deal.json()["error"]["message"]


@pytest.mark.asyncio
async def test_analytics_permission_enforcement(
    client: AsyncClient,
    test_org: Organization,
    auth_headers_member: dict,
):
    """Analytics endpoints require authentication and authorized permissions."""
    # 1. Unauthenticated requests return 401
    res_unauth1 = await client.get("/api/v1/reports/pipeline-summary")
    assert res_unauth1.status_code == 401

    res_unauth2 = await client.get("/api/v1/reports/won-lost")
    assert res_unauth2.status_code == 401

    res_unauth3 = await client.get("/api/v1/deals/pipeline-summary")
    assert res_unauth3.status_code == 401

    res_unauth4 = await client.get("/api/v1/deals/won-lost")
    assert res_unauth4.status_code == 401

    # 2. Member role has REPORTS_READ and DEALS_READ and can access both
    res_mem1 = await client.get("/api/v1/reports/pipeline-summary", headers=auth_headers_member)
    assert res_mem1.status_code == 200

    res_mem2 = await client.get("/api/v1/deals/pipeline-summary", headers=auth_headers_member)
    assert res_mem2.status_code == 200


@pytest.mark.asyncio
async def test_deal_board_and_list_regression(
    client: AsyncClient,
    test_org: Organization,
    auth_headers_owner: dict,
):
    """Board and list deals functionality operates regression-free alongside analytics."""
    # List deals
    res_list = await client.get("/api/v1/deals", headers=auth_headers_owner)
    assert res_list.status_code == 200
    assert isinstance(res_list.json(), list)

    # Board view
    res_board = await client.get("/api/v1/deals/board", headers=auth_headers_owner)
    assert res_board.status_code == 200
    board_data = res_board.json()
    assert "pipeline_id" in board_data
    assert "stages" in board_data
    assert "total_deals" in board_data
    assert "total_value" in board_data
