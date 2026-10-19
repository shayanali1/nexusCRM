import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.security import hash_password, create_access_token
from app.modules.deals.models import Deal, DealStatus
from app.modules.organizations.models import Organization
from app.modules.pipelines.models import Pipeline, PipelineStage
from app.modules.users.models import User


@pytest.mark.asyncio
async def test_pipeline_board_grouping_and_ordering(
    client: AsyncClient,
    test_org: Organization,
    auth_headers_owner: dict,
    db_session: AsyncSession,
):
    """Pipeline board retrieves every stage in deterministic order and groups deals correctly."""
    # 1. Create custom pipeline with 3 stages out of order in creation
    res_pipe = await client.post(
        "/api/v1/pipelines",
        json={
            "name": "Grouping Test Pipeline",
            "is_default": False,
            "stages": [
                {"name": "Stage 1 - Discovery", "order": 1, "win_probability": 20},
                {"name": "Stage 2 - Evaluation", "order": 2, "win_probability": 50},
                {"name": "Stage 3 - Won", "order": 3, "win_probability": 100, "is_won": True},
            ],
        },
        headers=auth_headers_owner,
    )
    assert res_pipe.status_code == 201
    pipe_data = res_pipe.json()
    pipe_id = pipe_data["id"]
    s1_id = pipe_data["stages"][0]["id"]
    s2_id = pipe_data["stages"][1]["id"]
    s3_id = pipe_data["stages"][2]["id"]

    # 2. Create deals: 2 in Stage 1, 0 in Stage 2, 1 in Stage 3
    res_d1 = await client.post(
        "/api/v1/deals",
        json={"title": "Deal 1 in S1", "pipeline_id": pipe_id, "stage_id": s1_id, "value": 15000.0},
        headers=auth_headers_owner,
    )
    assert res_d1.status_code == 201
    d1_id = res_d1.json()["id"]

    res_d2 = await client.post(
        "/api/v1/deals",
        json={"title": "Deal 2 in S1", "pipeline_id": pipe_id, "stage_id": s1_id, "value": 25000.0},
        headers=auth_headers_owner,
    )
    assert res_d2.status_code == 201
    d2_id = res_d2.json()["id"]

    res_d3 = await client.post(
        "/api/v1/deals",
        json={"title": "Deal 3 in S3", "pipeline_id": pipe_id, "stage_id": s3_id, "value": 50000.0},
        headers=auth_headers_owner,
    )
    assert res_d3.status_code == 201
    d3_id = res_d3.json()["id"]

    # 3. Retrieve board via /pipelines/{pipeline_id}/board
    res_board = await client.get(f"/api/v1/pipelines/{pipe_id}/board", headers=auth_headers_owner)
    assert res_board.status_code == 200
    board = res_board.json()

    assert board["pipeline_id"] == pipe_id
    assert board["pipeline_name"] == "Grouping Test Pipeline"
    assert board["is_default"] is False
    assert board["total_deals"] == 3
    assert board["total_value"] == 90000.0
    assert len(board["stages"]) == 3

    # Verify stage ordering
    assert [s["order"] for s in board["stages"]] == [1, 2, 3]
    assert board["stages"][0]["name"] == "Stage 1 - Discovery"
    assert board["stages"][1]["name"] == "Stage 2 - Evaluation"
    assert board["stages"][2]["name"] == "Stage 3 - Won"

    # Verify Stage 1 deals and deterministic ordering (newest first: d2 then d1)
    s1_resp = board["stages"][0]
    assert s1_resp["deal_count"] == 2
    assert s1_resp["total_value"] == 40000.0
    assert len(s1_resp["deals"]) == 2
    assert [d["id"] for d in s1_resp["deals"]] == [d2_id, d1_id]
    assert s1_resp["deals"][0]["stage_name"] == "Stage 1 - Discovery"

    # Verify Stage 2 (empty stage)
    s2_resp = board["stages"][1]
    assert s2_resp["deal_count"] == 0
    assert s2_resp["total_value"] == 0.0
    assert s2_resp["deals"] == []

    # Verify Stage 3 deals (WON stage)
    s3_resp = board["stages"][2]
    assert s3_resp["deal_count"] == 1
    assert s3_resp["total_value"] == 50000.0
    assert len(s3_resp["deals"]) == 1
    assert s3_resp["deals"][0]["id"] == d3_id


@pytest.mark.asyncio
async def test_pipeline_board_metric_accuracy_and_pagination(
    client: AsyncClient,
    test_org: Organization,
    auth_headers_owner: dict,
    db_session: AsyncSession,
):
    """Per-stage metrics are calculated from complete matching dataset, even when pagination caps cards."""
    res_pipe = await client.post(
        "/api/v1/pipelines",
        json={
            "name": "Metrics & Pagination Pipeline",
            "is_default": False,
            "stages": [
                {"name": "Heavy Stage", "order": 1, "win_probability": 25},
                {"name": "Light Stage", "order": 2, "win_probability": 75},
            ],
        },
        headers=auth_headers_owner,
    )
    assert res_pipe.status_code == 201
    pipe_data = res_pipe.json()
    pipe_id = pipe_data["id"]
    s1_id = pipe_data["stages"][0]["id"]
    s2_id = pipe_data["stages"][1]["id"]

    # Create 4 deals in Stage 1 ($10k, $20k, $30k, $40k = $100k total)
    deal_ids_s1 = []
    for val in [10000.0, 20000.0, 30000.0, 40000.0]:
        res_d = await client.post(
            "/api/v1/deals",
            json={"title": f"Deal {val}", "pipeline_id": pipe_id, "stage_id": s1_id, "value": val},
            headers=auth_headers_owner,
        )
        assert res_d.status_code == 201
        deal_ids_s1.append(res_d.json()["id"])

    # Create 1 deal in Stage 2 ($55k)
    res_s2 = await client.post(
        "/api/v1/deals",
        json={"title": "Single Deal S2", "pipeline_id": pipe_id, "stage_id": s2_id, "value": 55000.0},
        headers=auth_headers_owner,
    )
    assert res_s2.status_code == 201

    # Request board with limit_per_stage=2
    res_board = await client.get(
        f"/api/v1/pipelines/{pipe_id}/board?limit_per_stage=2",
        headers=auth_headers_owner,
    )
    assert res_board.status_code == 200
    board = res_board.json()

    # Overall totals reflect complete dataset
    assert board["total_deals"] == 5
    assert board["total_value"] == 155000.0

    # Stage 1: deal_count is 4 and total_value is 100,000 despite returning only 2 deal cards
    s1 = board["stages"][0]
    assert s1["deal_count"] == 4
    assert s1["total_value"] == 100000.0
    assert len(s1["deals"]) == 2  # capped by limit_per_stage=2

    # Stage 2: deal_count is 1, returns 1 card
    s2 = board["stages"][1]
    assert s2["deal_count"] == 1
    assert s2["total_value"] == 55000.0
    assert len(s2["deals"]) == 1


@pytest.mark.asyncio
async def test_pipeline_board_nullable_deal_values(
    client: AsyncClient,
    test_org: Organization,
    auth_headers_owner: dict,
    db_session: AsyncSession,
):
    """Deals with null or zero values are handled safely in aggregates and cards."""
    res_pipe = await client.post(
        "/api/v1/pipelines",
        json={
            "name": "Null Values Pipeline",
            "is_default": False,
            "stages": [
                {"name": "Stage Zero", "order": 1, "win_probability": 10},
            ],
        },
        headers=auth_headers_owner,
    )
    assert res_pipe.status_code == 201
    pipe_id = res_pipe.json()["id"]
    stage_id = res_pipe.json()["stages"][0]["id"]

    # 1. Deal with default 0.0 value
    res_d1 = await client.post(
        "/api/v1/deals",
        json={"title": "Zero Value Deal", "pipeline_id": pipe_id, "stage_id": stage_id, "value": 0.0},
        headers=auth_headers_owner,
    )
    assert res_d1.status_code == 201

    # 2. Insert deal with explicitly NULL value directly in DB
    null_deal = Deal(
        organization_id=test_org.id,
        pipeline_id=pipe_id,
        stage_id=stage_id,
        title="Null Value DB Deal",
        value=None,
    )
    db_session.add(null_deal)
    await db_session.commit()

    # 3. Deal with normal positive value
    res_d3 = await client.post(
        "/api/v1/deals",
        json={"title": "Normal Value Deal", "pipeline_id": pipe_id, "stage_id": stage_id, "value": 12500.0},
        headers=auth_headers_owner,
    )
    assert res_d3.status_code == 201

    # Retrieve board
    res_board = await client.get(f"/api/v1/pipelines/{pipe_id}/board", headers=auth_headers_owner)
    assert res_board.status_code == 200
    board = res_board.json()

    assert board["total_deals"] == 3
    assert board["total_value"] == 12500.0

    st = board["stages"][0]
    assert st["deal_count"] == 3
    assert st["total_value"] == 12500.0
    assert len(st["deals"]) == 3

    # Ensure the deal with null value is safely represented as 0.0 in the response
    null_card = next(d for d in st["deals"] if d["title"] == "Null Value DB Deal")
    assert null_card["value"] == 0.0


@pytest.mark.asyncio
async def test_pipeline_board_filters_assigned_to_status_search(
    client: AsyncClient,
    test_org: Organization,
    test_user_member: User,
    auth_headers_owner: dict,
    db_session: AsyncSession,
):
    """Filters (assigned_to_id, status, search) scope both metrics and card results."""
    # Create second member user
    rep2 = User(
        organization_id=test_org.id,
        email="rep2.board@alpha.com",
        hashed_password=hash_password("password123"),
        first_name="Bob",
        last_name="Sales",
        role="MEMBER",
        is_active=True,
    )
    db_session.add(rep2)
    await db_session.commit()

    res_pipe = await client.post(
        "/api/v1/pipelines",
        json={
            "name": "Filtered Pipeline",
            "is_default": False,
            "stages": [
                {"name": "Discovery", "order": 1, "win_probability": 20},
                {"name": "Won Stage", "order": 2, "win_probability": 100, "is_won": True},
            ],
        },
        headers=auth_headers_owner,
    )
    assert res_pipe.status_code == 201
    pipe_data = res_pipe.json()
    pipe_id = pipe_data["id"]
    s_open = pipe_data["stages"][0]["id"]
    s_won = pipe_data["stages"][1]["id"]

    # Deal A: Rep 1, Discovery, $30,000, title "Acme Cloud"
    await client.post(
        "/api/v1/deals",
        json={"title": "Acme Cloud", "pipeline_id": pipe_id, "stage_id": s_open, "assigned_to_id": test_user_member.id, "value": 30000.0},
        headers=auth_headers_owner,
    )

    # Deal B: Rep 2, Discovery, $70,000, title "Beta Security"
    await client.post(
        "/api/v1/deals",
        json={"title": "Beta Security", "pipeline_id": pipe_id, "stage_id": s_open, "assigned_to_id": rep2.id, "value": 70000.0},
        headers=auth_headers_owner,
    )

    # Deal C: Rep 1, Won Stage, $100,000, title "Acme Enterprise Won"
    res_c = await client.post(
        "/api/v1/deals",
        json={"title": "Acme Enterprise Won", "pipeline_id": pipe_id, "stage_id": s_open, "assigned_to_id": test_user_member.id, "value": 100000.0},
        headers=auth_headers_owner,
    )
    deal_c_id = res_c.json()["id"]
    await client.post(f"/api/v1/deals/{deal_c_id}/move-stage", json={"stage_id": s_won}, headers=auth_headers_owner)

    # 1. Filter by assigned_to_id = rep2.id
    res_rep2 = await client.get(f"/api/v1/pipelines/{pipe_id}/board?assigned_to_id={rep2.id}", headers=auth_headers_owner)
    assert res_rep2.status_code == 200
    b_rep2 = res_rep2.json()
    assert b_rep2["total_deals"] == 1
    assert b_rep2["total_value"] == 70000.0
    assert b_rep2["stages"][0]["deal_count"] == 1
    assert b_rep2["stages"][1]["deal_count"] == 0

    # 2. Filter by status = "OPEN" -> Won stage metrics become 0
    res_open = await client.get(f"/api/v1/pipelines/{pipe_id}/board?status=OPEN", headers=auth_headers_owner)
    assert res_open.status_code == 200
    b_open = res_open.json()
    assert b_open["total_deals"] == 2
    assert b_open["total_value"] == 100000.0
    assert b_open["stages"][1]["deal_count"] == 0
    assert b_open["stages"][1]["total_value"] == 0.0

    # 3. Filter by search = "Acme"
    res_search = await client.get(f"/api/v1/pipelines/{pipe_id}/board?search=Acme", headers=auth_headers_owner)
    assert res_search.status_code == 200
    b_search = res_search.json()
    assert b_search["total_deals"] == 2
    assert b_search["total_value"] == 130000.0


@pytest.mark.asyncio
async def test_pipeline_board_empty_pipeline_and_invalid_ids(
    client: AsyncClient,
    test_org: Organization,
    auth_headers_owner: dict,
    db_session: AsyncSession,
):
    """Empty pipeline returns 200 with empty stages; invalid ID returns 404."""
    # 1. Pipeline with no stages
    stageless = Pipeline(organization_id=test_org.id, name="Empty Pipeline", is_default=False)
    db_session.add(stageless)
    await db_session.commit()

    res_empty = await client.get(f"/api/v1/pipelines/{stageless.id}/board", headers=auth_headers_owner)
    assert res_empty.status_code == 200
    b_empty = res_empty.json()
    assert b_empty["pipeline_id"] == stageless.id
    assert b_empty["stages"] == []
    assert b_empty["total_deals"] == 0
    assert b_empty["total_value"] == 0.0

    # 2. Non-existent pipeline ID -> 404
    res_404 = await client.get("/api/v1/pipelines/00000000-0000-0000-0000-000000000000/board", headers=auth_headers_owner)
    assert res_404.status_code == 404
    assert "Pipeline not found" in res_404.json()["error"]["message"]


@pytest.mark.asyncio
async def test_pipeline_board_cross_tenant_isolation(
    client: AsyncClient,
    test_org: Organization,
    auth_headers_owner: dict,
    db_session: AsyncSession,
):
    """Org A cannot view Org B's pipeline board; Org B deals never leak into Org A board."""
    org_b = Organization(name="Tenant Omega", slug="tenant-omega", is_active=True)
    db_session.add(org_b)
    await db_session.flush()

    pipe_b = Pipeline(organization_id=org_b.id, name="Omega Confidential Pipeline", is_default=True)
    db_session.add(pipe_b)
    await db_session.flush()

    stage_b = PipelineStage(organization_id=org_b.id, pipeline_id=pipe_b.id, name="Omega Secret Stage", order=1)
    db_session.add(stage_b)
    await db_session.flush()

    deal_b = Deal(
        organization_id=org_b.id,
        pipeline_id=pipe_b.id,
        stage_id=stage_b.id,
        title="Omega Secret Deal",
        value=500000.0,
    )
    db_session.add(deal_b)
    await db_session.commit()

    # 1. Org A cannot access Org B's pipeline board -> 404
    res_pipe_b = await client.get(f"/api/v1/pipelines/{pipe_b.id}/board", headers=auth_headers_owner)
    assert res_pipe_b.status_code == 404

    # 2. Org A via /deals/board?pipeline_id=... cannot access Org B's pipeline -> 404
    res_deals_b = await client.get(f"/api/v1/deals/board?pipeline_id={pipe_b.id}", headers=auth_headers_owner)
    assert res_deals_b.status_code == 404

    # 3. Org A's own default board never contains Org B's deals or values
    res_a_board = await client.get("/api/v1/deals/board", headers=auth_headers_owner)
    assert res_a_board.status_code == 200
    a_board = res_a_board.json()
    all_deal_ids_in_a = [
        d["id"]
        for st in a_board["stages"]
        for d in st["deals"]
    ]
    assert deal_b.id not in all_deal_ids_in_a


@pytest.mark.asyncio
async def test_deals_board_and_pipeline_board_parity(
    client: AsyncClient,
    test_org: Organization,
    auth_headers_owner: dict,
    db_session: AsyncSession,
):
    """GET /deals/board and GET /pipelines/{pipeline_id}/board return equivalent structures."""
    # Find default pipeline of test_org
    def_stmt = select(Pipeline).where(Pipeline.organization_id == test_org.id, Pipeline.is_default.is_(True))
    default_pipe = (await db_session.execute(def_stmt)).scalars().first()
    assert default_pipe is not None

    # Call /pipelines/{default_pipe.id}/board
    res_pipe = await client.get(f"/api/v1/pipelines/{default_pipe.id}/board", headers=auth_headers_owner)
    assert res_pipe.status_code == 200

    # Call /deals/board (with default pipeline fallback)
    res_deals_def = await client.get("/api/v1/deals/board", headers=auth_headers_owner)
    assert res_deals_def.status_code == 200

    # Call /deals/board?pipeline_id=...
    res_deals_explicit = await client.get(f"/api/v1/deals/board?pipeline_id={default_pipe.id}", headers=auth_headers_owner)
    assert res_deals_explicit.status_code == 200

    # Verify matching pipeline metadata and metrics
    data_pipe = res_pipe.json()
    data_deals_def = res_deals_def.json()
    data_deals_exp = res_deals_explicit.json()

    assert data_pipe["pipeline_id"] == data_deals_def["pipeline_id"] == data_deals_exp["pipeline_id"]
    assert data_pipe["total_deals"] == data_deals_def["total_deals"] == data_deals_exp["total_deals"]
    assert data_pipe["total_value"] == data_deals_def["total_value"] == data_deals_exp["total_value"]
    assert len(data_pipe["stages"]) == len(data_deals_def["stages"]) == len(data_deals_exp["stages"])
