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
async def test_create_and_retrieve_pipeline_with_stages(
    client: AsyncClient,
    test_org: Organization,
    auth_headers_owner: dict,
    db_session: AsyncSession,
):
    """Create a new sales pipeline with nested stages and verify structure."""
    payload = {
        "name": "Mid-Market Sales Pipeline",
        "is_default": False,
        "stages": [
            {"name": "Initial Outreach", "order": 1, "win_probability": 10},
            {"name": "Product Demonstration", "order": 2, "win_probability": 40},
            {"name": "Proposal & Pricing", "order": 3, "win_probability": 75},
            {"name": "Closed Won", "order": 4, "win_probability": 100, "is_won": True, "is_lost": False},
            {"name": "Closed Lost", "order": 5, "win_probability": 0, "is_won": False, "is_lost": True},
        ],
    }
    res = await client.post("/api/v1/pipelines", json=payload, headers=auth_headers_owner)
    assert res.status_code == 201
    pipe_data = res.json()
    assert pipe_data["name"] == "Mid-Market Sales Pipeline"
    assert pipe_data["is_default"] is False
    assert len(pipe_data["stages"]) == 5
    assert pipe_data["stages"][0]["name"] == "Initial Outreach"
    assert pipe_data["stages"][3]["is_won"] is True
    assert pipe_data["stages"][4]["is_lost"] is True

    pipe_id = pipe_data["id"]

    # Retrieve single pipeline
    res_get = await client.get(f"/api/v1/pipelines/{pipe_id}", headers=auth_headers_owner)
    assert res_get.status_code == 200
    assert res_get.json()["id"] == pipe_id
    assert len(res_get.json()["stages"]) == 5


@pytest.mark.asyncio
async def test_pipeline_default_flag_toggling(
    client: AsyncClient,
    test_org: Organization,
    auth_headers_owner: dict,
    db_session: AsyncSession,
):
    """Setting is_default on a pipeline unsets it on other pipelines in the organization."""
    # 1. Get current default pipeline
    def_pipe_stmt = select(Pipeline).where(Pipeline.organization_id == test_org.id, Pipeline.is_default.is_(True))
    orig_default = (await db_session.execute(def_pipe_stmt)).scalars().first()
    assert orig_default is not None

    # 2. Create second pipeline with is_default=True
    res_create = await client.post(
        "/api/v1/pipelines",
        json={"name": "New Default Pipeline", "is_default": True},
        headers=auth_headers_owner,
    )
    assert res_create.status_code == 201
    new_pipe_id = res_create.json()["id"]

    # Verify new pipeline is default, and original default is unset
    new_pipe_db = (await db_session.execute(select(Pipeline).where(Pipeline.id == new_pipe_id))).scalar_one()
    assert new_pipe_db.is_default is True

    orig_pipe_db = (await db_session.execute(select(Pipeline).where(Pipeline.id == orig_default.id))).scalar_one()
    assert orig_pipe_db.is_default is False

    # 3. Patch original pipeline to be default again
    res_patch = await client.patch(
        f"/api/v1/pipelines/{orig_default.id}",
        json={"is_default": True},
        headers=auth_headers_owner,
    )
    assert res_patch.status_code == 200
    assert res_patch.json()["is_default"] is True

    new_pipe_db = (await db_session.execute(select(Pipeline).where(Pipeline.id == new_pipe_id))).scalar_one()
    assert new_pipe_db.is_default is False

    # 4. Attempt to delete default pipeline -> rejected with 400
    res_del_def = await client.delete(f"/api/v1/pipelines/{orig_default.id}", headers=auth_headers_owner)
    assert res_del_def.status_code == 400
    assert "Cannot delete the default sales pipeline" in res_del_def.json()["error"]["message"]


@pytest.mark.asyncio
async def test_add_and_update_pipeline_stages(
    client: AsyncClient,
    test_org: Organization,
    auth_headers_owner: dict,
    db_session: AsyncSession,
):
    """Add new stage and update existing stage properties and order."""
    # Create isolated custom pipeline
    res_pipe = await client.post(
        "/api/v1/pipelines",
        json={"name": "Staging Pipeline", "is_default": False},
        headers=auth_headers_owner,
    )
    assert res_pipe.status_code == 201
    pipe_id = res_pipe.json()["id"]

    # 1. Add stage
    res_stage = await client.post(
        f"/api/v1/pipelines/{pipe_id}/stages",
        json={"name": "Discovery", "order": 1, "win_probability": 20},
        headers=auth_headers_owner,
    )
    assert res_stage.status_code == 201
    stage_data = res_stage.json()
    stage_id = stage_data["id"]
    assert stage_data["name"] == "Discovery"
    assert stage_data["win_probability"] == 20

    # 2. Update stage
    res_update = await client.patch(
        f"/api/v1/pipelines/{pipe_id}/stages/{stage_id}",
        json={"name": "Qualified Discovery", "win_probability": 25, "order": 2},
        headers=auth_headers_owner,
    )
    assert res_update.status_code == 200
    updated_data = res_update.json()
    assert updated_data["name"] == "Qualified Discovery"
    assert updated_data["win_probability"] == 25
    assert updated_data["order"] == 2


@pytest.mark.asyncio
async def test_stage_won_and_lost_mutual_exclusivity(
    client: AsyncClient,
    test_org: Organization,
    auth_headers_owner: dict,
    db_session: AsyncSession,
):
    """A stage cannot be configured as both won and lost simultaneously."""
    res_pipe = await client.post(
        "/api/v1/pipelines",
        json={"name": "Validation Pipeline", "is_default": False},
        headers=auth_headers_owner,
    )
    assert res_pipe.status_code == 201
    pipe_id = res_pipe.json()["id"]

    # 1. Reject add_stage with both is_won and is_lost True
    res_add = await client.post(
        f"/api/v1/pipelines/{pipe_id}/stages",
        json={"name": "Paradox Stage", "order": 1, "is_won": True, "is_lost": True},
        headers=auth_headers_owner,
    )
    assert res_add.status_code in (400, 422)

    # 2. Create normal stage
    res_normal = await client.post(
        f"/api/v1/pipelines/{pipe_id}/stages",
        json={"name": "Normal Stage", "order": 1, "is_won": True, "is_lost": False},
        headers=auth_headers_owner,
    )
    assert res_normal.status_code == 201
    stage_id = res_normal.json()["id"]

    # 3. Reject update stage setting is_lost=True while is_won=True
    res_patch = await client.patch(
        f"/api/v1/pipelines/{pipe_id}/stages/{stage_id}",
        json={"is_lost": True},
        headers=auth_headers_owner,
    )
    assert res_patch.status_code in (400, 422)


@pytest.mark.asyncio
async def test_stage_deletion_with_deals_prevented(
    client: AsyncClient,
    test_org: Organization,
    auth_headers_owner: dict,
    db_session: AsyncSession,
):
    """Deleting a stage that contains deals is rejected with 400."""
    # Create pipeline with two stages
    res_pipe = await client.post(
        "/api/v1/pipelines",
        json={
            "name": "Stage Delete Protection Pipeline",
            "is_default": False,
            "stages": [
                {"name": "Stage Alpha", "order": 1, "win_probability": 10},
                {"name": "Stage Beta", "order": 2, "win_probability": 90},
            ],
        },
        headers=auth_headers_owner,
    )
    assert res_pipe.status_code == 201
    pipe_data = res_pipe.json()
    pipe_id = pipe_data["id"]
    stage_alpha_id = pipe_data["stages"][0]["id"]
    stage_beta_id = pipe_data["stages"][1]["id"]

    # Create a deal in Stage Alpha
    deal = Deal(
        organization_id=test_org.id,
        pipeline_id=pipe_id,
        stage_id=stage_alpha_id,
        title="Active Deal in Stage Alpha",
        value=50000.0,
    )
    db_session.add(deal)
    await db_session.commit()
    await db_session.refresh(deal)

    # 1. Attempt to delete Stage Alpha -> Rejected because deal is in it
    res_del_alpha = await client.delete(
        f"/api/v1/pipelines/{pipe_id}/stages/{stage_alpha_id}",
        headers=auth_headers_owner,
    )
    assert res_del_alpha.status_code == 400
    assert "Cannot delete pipeline stage containing" in res_del_alpha.json()["error"]["message"]

    # 2. Move deal to Stage Beta
    res_move = await client.post(
        f"/api/v1/deals/{deal.id}/move-stage",
        json={"stage_id": stage_beta_id},
        headers=auth_headers_owner,
    )
    assert res_move.status_code == 200

    # 3. Stage Alpha is now empty and can be deleted
    res_del_alpha_ok = await client.delete(
        f"/api/v1/pipelines/{pipe_id}/stages/{stage_alpha_id}",
        headers=auth_headers_owner,
    )
    assert res_del_alpha_ok.status_code == 204

    # 4. Attempt to delete Stage Beta -> Rejected because it is now the ONLY stage in the pipeline
    res_del_beta_only = await client.delete(
        f"/api/v1/pipelines/{pipe_id}/stages/{stage_beta_id}",
        headers=auth_headers_owner,
    )
    assert res_del_beta_only.status_code == 400


@pytest.mark.asyncio
async def test_pipeline_deletion_with_deals_prevented(
    client: AsyncClient,
    test_org: Organization,
    auth_headers_owner: dict,
    db_session: AsyncSession,
):
    """Deleting a non-default pipeline that contains deals is rejected with 400."""
    res_pipe = await client.post(
        "/api/v1/pipelines",
        json={
            "name": "Pipeline Deletion Guard",
            "is_default": False,
            "stages": [
                {"name": "Step 1", "order": 1, "win_probability": 20},
                {"name": "Step 2", "order": 2, "win_probability": 80},
            ],
        },
        headers=auth_headers_owner,
    )
    assert res_pipe.status_code == 201
    pipe_data = res_pipe.json()
    pipe_id = pipe_data["id"]
    stage_id = pipe_data["stages"][0]["id"]

    # Create deal in this pipeline
    deal = Deal(
        organization_id=test_org.id,
        pipeline_id=pipe_id,
        stage_id=stage_id,
        title="Blocking Deal",
        value=30000.0,
    )
    db_session.add(deal)
    await db_session.commit()
    await db_session.refresh(deal)

    # Attempt to delete pipeline -> Rejected
    res_del = await client.delete(f"/api/v1/pipelines/{pipe_id}", headers=auth_headers_owner)
    assert res_del.status_code == 400
    assert "Cannot delete pipeline containing" in res_del.json()["error"]["message"]

    # Delete deal
    res_deal_del = await client.delete(f"/api/v1/deals/{deal.id}", headers=auth_headers_owner)
    assert res_deal_del.status_code == 204

    # Now pipeline can be deleted
    res_pipe_del = await client.delete(f"/api/v1/pipelines/{pipe_id}", headers=auth_headers_owner)
    assert res_pipe_del.status_code == 204

    # Verify pipeline is gone
    res_chk = await client.get(f"/api/v1/pipelines/{pipe_id}", headers=auth_headers_owner)
    assert res_chk.status_code == 404


@pytest.mark.asyncio
async def test_cross_tenant_pipeline_and_stage_isolation(
    client: AsyncClient,
    test_org: Organization,
    auth_headers_owner: dict,
    db_session: AsyncSession,
):
    """Org A cannot view, update, delete, or manage Org B pipelines and stages."""
    org_b = Organization(name="Tenant Gamma", slug="tenant-gamma", is_active=True)
    db_session.add(org_b)
    await db_session.flush()

    pipe_b = Pipeline(organization_id=org_b.id, name="Gamma Confidential Pipeline", is_default=True)
    db_session.add(pipe_b)
    await db_session.flush()

    stage_b = PipelineStage(
        organization_id=org_b.id,
        pipeline_id=pipe_b.id,
        name="Gamma Secret Stage",
        order=1,
    )
    db_session.add(stage_b)
    await db_session.commit()

    # 1. Org A cannot GET Org B pipeline
    res_get = await client.get(f"/api/v1/pipelines/{pipe_b.id}", headers=auth_headers_owner)
    assert res_get.status_code == 404

    # 2. Org A cannot PATCH Org B pipeline
    res_patch = await client.patch(
        f"/api/v1/pipelines/{pipe_b.id}",
        json={"name": "Hacked Pipeline"},
        headers=auth_headers_owner,
    )
    assert res_patch.status_code == 404

    # 3. Org A cannot DELETE Org B pipeline
    res_del = await client.delete(f"/api/v1/pipelines/{pipe_b.id}", headers=auth_headers_owner)
    assert res_del.status_code == 404

    # 4. Org A cannot add stage to Org B pipeline
    res_add_stage = await client.post(
        f"/api/v1/pipelines/{pipe_b.id}/stages",
        json={"name": "Infiltrator Stage", "order": 2},
        headers=auth_headers_owner,
    )
    assert res_add_stage.status_code == 404

    # 5. Org A cannot PATCH Org B stage
    res_patch_stage = await client.patch(
        f"/api/v1/pipelines/{pipe_b.id}/stages/{stage_b.id}",
        json={"name": "Hacked Stage"},
        headers=auth_headers_owner,
    )
    assert res_patch_stage.status_code == 404

    # 6. Org A cannot DELETE Org B stage
    res_del_stage = await client.delete(
        f"/api/v1/pipelines/{pipe_b.id}/stages/{stage_b.id}",
        headers=auth_headers_owner,
    )
    assert res_del_stage.status_code == 404


@pytest.mark.asyncio
async def test_deal_lifecycle_state_consistency(
    client: AsyncClient,
    test_org: Organization,
    auth_headers_owner: dict,
    db_session: AsyncSession,
):
    """Deal won/lost lifecycle states and timestamps are maintained consistently across transitions."""
    # Create pipeline with Open, Won, and Lost stages
    res_pipe = await client.post(
        "/api/v1/pipelines",
        json={
            "name": "Lifecycle Test Pipeline",
            "is_default": False,
            "stages": [
                {"name": "Negotiation", "order": 1, "win_probability": 60, "is_won": False, "is_lost": False},
                {"name": "Signed & Won", "order": 2, "win_probability": 100, "is_won": True, "is_lost": False},
                {"name": "Disqualified Lost", "order": 3, "win_probability": 0, "is_won": False, "is_lost": True},
            ],
        },
        headers=auth_headers_owner,
    )
    assert res_pipe.status_code == 201
    pipe_data = res_pipe.json()
    pipe_id = pipe_data["id"]
    stage_open_id = pipe_data["stages"][0]["id"]
    stage_won_id = pipe_data["stages"][1]["id"]
    stage_lost_id = pipe_data["stages"][2]["id"]

    # 1. Create deal in open stage
    res_deal = await client.post(
        "/api/v1/deals",
        json={"title": "Lifecycle Deal", "pipeline_id": pipe_id, "stage_id": stage_open_id, "value": 75000.0},
        headers=auth_headers_owner,
    )
    assert res_deal.status_code == 201
    deal_id = res_deal.json()["id"]

    deal_db = (await db_session.execute(select(Deal).where(Deal.id == deal_id))).scalar_one()
    assert deal_db.status == "OPEN"
    assert deal_db.closed_at is None
    assert deal_db.lost_reason is None

    # 2. Move deal to WON stage
    res_won = await client.post(
        f"/api/v1/deals/{deal_id}/move-stage",
        json={"stage_id": stage_won_id},
        headers=auth_headers_owner,
    )
    assert res_won.status_code == 200
    assert res_won.json()["status"] == "WON"
    assert res_won.json()["closed_at"] is not None

    deal_db = (await db_session.execute(select(Deal).where(Deal.id == deal_id))).scalar_one()
    assert deal_db.status == "WON"
    assert deal_db.closed_at is not None
    assert deal_db.lost_reason is None

    # 3. Move deal to LOST stage with lost_reason
    res_lost = await client.post(
        f"/api/v1/deals/{deal_id}/move-stage",
        json={"stage_id": stage_lost_id, "lost_reason": "Competitor won on pricing"},
        headers=auth_headers_owner,
    )
    assert res_lost.status_code == 200
    assert res_lost.json()["status"] == "LOST"
    assert res_lost.json()["lost_reason"] == "Competitor won on pricing"
    assert res_lost.json()["closed_at"] is not None

    deal_db = (await db_session.execute(select(Deal).where(Deal.id == deal_id))).scalar_one()
    assert deal_db.status == "LOST"
    assert deal_db.lost_reason == "Competitor won on pricing"
    assert deal_db.closed_at is not None

    # 4. Move deal back to OPEN stage -> clears closed_at and lost_reason
    res_reopen = await client.post(
        f"/api/v1/deals/{deal_id}/move-stage",
        json={"stage_id": stage_open_id},
        headers=auth_headers_owner,
    )
    assert res_reopen.status_code == 200
    assert res_reopen.json()["status"] == "OPEN"
    assert res_reopen.json()["closed_at"] is None
    assert res_reopen.json()["lost_reason"] is None

    deal_db = (await db_session.execute(select(Deal).where(Deal.id == deal_id))).scalar_one()
    assert deal_db.status == "OPEN"
    assert deal_db.closed_at is None
    assert deal_db.lost_reason is None

    # 5. Reject contradictory state: moving to won stage with status="LOST"
    res_contra = await client.post(
        f"/api/v1/deals/{deal_id}/move-stage",
        json={"stage_id": stage_won_id, "status": "LOST"},
        headers=auth_headers_owner,
    )
    assert res_contra.status_code == 400
    assert "Cannot assign a non-WON status" in res_contra.json()["error"]["message"]


@pytest.mark.asyncio
async def test_cannot_directly_unset_default_pipeline_in_multi_pipeline_org(
    client: AsyncClient,
    test_org: Organization,
    auth_headers_owner: dict,
    db_session: AsyncSession,
):
    """An organization with multiple pipelines cannot directly unset its default pipeline."""
    # 1. Retrieve the existing default pipeline
    def_pipe_stmt = select(Pipeline).where(Pipeline.organization_id == test_org.id, Pipeline.is_default.is_(True))
    orig_default = (await db_session.execute(def_pipe_stmt)).scalars().first()
    assert orig_default is not None

    # Create secondary non-default pipeline so the organization has two pipelines
    res_create = await client.post(
        "/api/v1/pipelines",
        json={"name": "Secondary Pipeline", "is_default": False},
        headers=auth_headers_owner,
    )
    assert res_create.status_code == 201
    sec_pipe_id = res_create.json()["id"]

    # 1. An organization with two pipelines cannot directly unset its current default
    res_unset = await client.patch(
        f"/api/v1/pipelines/{orig_default.id}",
        json={"is_default": False},
        headers=auth_headers_owner,
    )
    assert res_unset.status_code == 400
    assert "Cannot unset the default sales pipeline" in res_unset.json()["error"]["message"]

    # 2. The rejected request leaves the original default unchanged
    orig_pipe_db = (await db_session.execute(select(Pipeline).where(Pipeline.id == orig_default.id))).scalar_one()
    assert orig_pipe_db.is_default is True

    sec_pipe_db = (await db_session.execute(select(Pipeline).where(Pipeline.id == sec_pipe_id))).scalar_one()
    assert sec_pipe_db.is_default is False

    # 3. Setting the second pipeline as default successfully switches the default
    res_switch = await client.patch(
        f"/api/v1/pipelines/{sec_pipe_id}",
        json={"is_default": True},
        headers=auth_headers_owner,
    )
    assert res_switch.status_code == 200
    assert res_switch.json()["is_default"] is True

    # 4. Exactly one default remains after the switch
    sec_pipe_db = (await db_session.execute(select(Pipeline).where(Pipeline.id == sec_pipe_id))).scalar_one()
    assert sec_pipe_db.is_default is True

    orig_pipe_db = (await db_session.execute(select(Pipeline).where(Pipeline.id == orig_default.id))).scalar_one()
    assert orig_pipe_db.is_default is False

    default_count = (await db_session.execute(
        select(func.count(Pipeline.id)).where(
            Pipeline.organization_id == test_org.id,
            Pipeline.is_default.is_(True),
        )
    )).scalar()
    assert default_count == 1


@pytest.mark.asyncio
async def test_deal_patch_stage_reopens_won_and_lost_deals_consistently(
    client: AsyncClient,
    test_org: Organization,
    auth_headers_owner: dict,
    db_session: AsyncSession,
):
    """PATCH moving a WON or LOST deal to an ordinary stage reopens it with cleared closed_at and lost_reason."""
    res_pipe = await client.post(
        "/api/v1/pipelines",
        json={
            "name": "PATCH Reopen Invariant Pipeline",
            "is_default": False,
            "stages": [
                {"name": "Ordinary Stage", "order": 1, "win_probability": 30, "is_won": False, "is_lost": False},
                {"name": "Won Stage", "order": 2, "win_probability": 100, "is_won": True, "is_lost": False},
                {"name": "Lost Stage", "order": 3, "win_probability": 0, "is_won": False, "is_lost": True},
            ],
        },
        headers=auth_headers_owner,
    )
    assert res_pipe.status_code == 201
    pipe_data = res_pipe.json()
    pipe_id = pipe_data["id"]
    stage_ord_id = pipe_data["stages"][0]["id"]
    stage_won_id = pipe_data["stages"][1]["id"]
    stage_lost_id = pipe_data["stages"][2]["id"]

    # 1. Create deal in WON stage via move-stage
    res_deal_won = await client.post(
        "/api/v1/deals",
        json={"title": "Won Deal To Reopen", "pipeline_id": pipe_id, "stage_id": stage_ord_id, "value": 60000.0},
        headers=auth_headers_owner,
    )
    assert res_deal_won.status_code == 201
    deal_won_id = res_deal_won.json()["id"]

    res_move_won = await client.post(
        f"/api/v1/deals/{deal_won_id}/move-stage",
        json={"stage_id": stage_won_id},
        headers=auth_headers_owner,
    )
    assert res_move_won.status_code == 200
    assert res_move_won.json()["status"] == "WON"
    assert res_move_won.json()["closed_at"] is not None

    # PATCH moving WON deal to ordinary stage reopens it
    res_patch_won = await client.patch(
        f"/api/v1/deals/{deal_won_id}",
        json={"stage_id": stage_ord_id},
        headers=auth_headers_owner,
    )
    assert res_patch_won.status_code == 200
    patch_won_data = res_patch_won.json()
    assert patch_won_data["status"] == "OPEN"
    assert patch_won_data["closed_at"] is None
    assert patch_won_data["lost_reason"] is None

    # Verify direct DB state for reopened WON deal
    db_won_deal = (await db_session.execute(select(Deal).where(Deal.id == deal_won_id))).scalar_one()
    assert db_won_deal.status == "OPEN"
    assert db_won_deal.closed_at is None
    assert db_won_deal.lost_reason is None

    # 2. Create deal and move to LOST stage with lost_reason
    res_deal_lost = await client.post(
        "/api/v1/deals",
        json={"title": "Lost Deal To Reopen", "pipeline_id": pipe_id, "stage_id": stage_ord_id, "value": 45000.0},
        headers=auth_headers_owner,
    )
    assert res_deal_lost.status_code == 201
    deal_lost_id = res_deal_lost.json()["id"]

    res_move_lost = await client.post(
        f"/api/v1/deals/{deal_lost_id}/move-stage",
        json={"stage_id": stage_lost_id, "lost_reason": "Price too high"},
        headers=auth_headers_owner,
    )
    assert res_move_lost.status_code == 200
    assert res_move_lost.json()["status"] == "LOST"
    assert res_move_lost.json()["closed_at"] is not None
    assert res_move_lost.json()["lost_reason"] == "Price too high"

    # PATCH moving LOST deal to ordinary stage reopens it
    res_patch_lost = await client.patch(
        f"/api/v1/deals/{deal_lost_id}",
        json={"stage_id": stage_ord_id},
        headers=auth_headers_owner,
    )
    assert res_patch_lost.status_code == 200
    patch_lost_data = res_patch_lost.json()
    assert patch_lost_data["status"] == "OPEN"
    assert patch_lost_data["closed_at"] is None
    assert patch_lost_data["lost_reason"] is None

    # Verify direct DB state for reopened LOST deal
    db_lost_deal = (await db_session.execute(select(Deal).where(Deal.id == deal_lost_id))).scalar_one()
    assert db_lost_deal.status == "OPEN"
    assert db_lost_deal.closed_at is None
    assert db_lost_deal.lost_reason is None

    # 3. Reject explicitly supplied contradictory status values via PATCH
    res_contra_patch = await client.patch(
        f"/api/v1/deals/{deal_won_id}",
        json={"stage_id": stage_ord_id, "status": "WON"},
        headers=auth_headers_owner,
    )
    assert res_contra_patch.status_code == 400
    assert "Cannot assign a non-OPEN status" in res_contra_patch.json()["error"]["message"]
