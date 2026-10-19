import pytest
import pytest_asyncio
from datetime import datetime, timezone, timedelta
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.security import create_access_token, hash_password
from app.modules.companies.models import Company
from app.modules.contacts.models import Contact
from app.modules.deals.models import Deal, DealStatus
from app.modules.organizations.models import Organization
from app.modules.pipelines.models import Pipeline, PipelineStage
from app.modules.users.models import User


@pytest_asyncio.fixture(scope="function")
async def seed_deals_data(
    db_session: AsyncSession,
    test_org: Organization,
    test_user_owner: User,
    test_user_member: User,
):
    """Seed comprehensive deals, pipelines, stages, contacts, and companies for Org A and Org B."""
    base_time = datetime(2026, 3, 1, 12, 0, 0, tzinfo=timezone.utc)

    # 1. Org B (Tenant Isolation)
    org_b = Organization(name="Tenant B", slug="tenant-b", is_active=True)
    db_session.add(org_b)
    await db_session.flush()

    user_b = User(
        organization_id=org_b.id,
        email="owner@tenantb.com",
        hashed_password=hash_password("password123"),
        first_name="Bob",
        last_name="TenantB",
        role="OWNER",
        is_active=True,
    )
    db_session.add(user_b)
    await db_session.flush()

    pipe_b = Pipeline(organization_id=org_b.id, name="Tenant B Pipeline", is_default=True)
    db_session.add(pipe_b)
    await db_session.flush()

    stage_b = PipelineStage(
        organization_id=org_b.id,
        pipeline_id=pipe_b.id,
        name="Tenant B Stage",
        order=1,
        win_probability=50,
    )
    db_session.add(stage_b)
    await db_session.flush()

    comp_b = Company(
        organization_id=org_b.id,
        name="Omega Industries",
        domain="omega.com",
    )
    db_session.add(comp_b)
    await db_session.flush()

    contact_b = Contact(
        organization_id=org_b.id,
        company_id=comp_b.id,
        first_name="Victor",
        last_name="Von",
        email="victor@omega.com",
    )
    db_session.add(contact_b)
    await db_session.flush()

    deal_b = Deal(
        id="90000000-0000-0000-0000-000000000001",
        organization_id=org_b.id,
        pipeline_id=pipe_b.id,
        stage_id=stage_b.id,
        contact_id=contact_b.id,
        company_id=comp_b.id,
        assigned_to_id=user_b.id,
        title="Alpha Foreign Deal In Org B",
        value=999999.0,
        status=DealStatus.OPEN.value,
        created_at=base_time + timedelta(days=1),
        updated_at=base_time + timedelta(days=1),
    )
    db_session.add(deal_b)

    # 2. Org A Setup
    # Pipeline 1 (default already created in test_org fixture, but let's configure explicit stages)
    # Get existing pipeline 1 in test_org
    pipe_1 = (await db_session.execute(
        Pipeline.__table__.select().where(Pipeline.organization_id == test_org.id)
    )).first()
    pipe_1_id = pipe_1.id

    stage_1_1 = (await db_session.execute(
        PipelineStage.__table__.select().where(PipelineStage.pipeline_id == pipe_1_id)
    )).first()
    s1_id = stage_1_1.id

    stage_1_2 = PipelineStage(
        organization_id=test_org.id,
        pipeline_id=pipe_1_id,
        name="Proposal",
        order=2,
        win_probability=60,
    )
    db_session.add(stage_1_2)
    await db_session.flush()
    s2_id = stage_1_2.id

    # Pipeline 2 in Org A
    pipe_2 = Pipeline(organization_id=test_org.id, name="Enterprise Pipeline", is_default=False)
    db_session.add(pipe_2)
    await db_session.flush()
    pipe_2_id = pipe_2.id

    stage_2_1 = PipelineStage(
        organization_id=test_org.id,
        pipeline_id=pipe_2_id,
        name="Discovery",
        order=1,
        win_probability=20,
    )
    stage_2_2 = PipelineStage(
        organization_id=test_org.id,
        pipeline_id=pipe_2_id,
        name="Negotiation",
        order=2,
        win_probability=80,
    )
    db_session.add_all([stage_2_1, stage_2_2])
    await db_session.flush()
    s3_id = stage_2_1.id
    s4_id = stage_2_2.id

    # Companies in Org A
    comp_a1 = Company(
        id="10000000-0000-0000-0000-000000000001",
        organization_id=test_org.id,
        name="Acme Corp",
        domain="acme.com",
    )
    comp_a2 = Company(
        id="10000000-0000-0000-0000-000000000002",
        organization_id=test_org.id,
        name="Beta Logistics",
        domain="betalogistics.com",
    )
    db_session.add_all([comp_a1, comp_a2])
    await db_session.flush()

    # Contacts in Org A
    cont_a1 = Contact(
        id="20000000-0000-0000-0000-000000000001",
        organization_id=test_org.id,
        company_id=comp_a1.id,
        first_name="Alice",
        last_name="Anderson",
        email="alice@acme.com",
    )
    cont_a2 = Contact(
        id="20000000-0000-0000-0000-000000000002",
        organization_id=test_org.id,
        company_id=comp_a2.id,
        first_name="Bob",
        last_name="Baker",
        email="bob@betalogistics.com",
    )
    db_session.add_all([cont_a1, cont_a2])
    await db_session.flush()

    # 5 Deals in Org A
    # D1: Alpha Enterprise SaaS
    deal_1 = Deal(
        id="30000000-0000-0000-0000-000000000001",
        organization_id=test_org.id,
        pipeline_id=pipe_1_id,
        stage_id=s1_id,
        contact_id=cont_a1.id,
        company_id=comp_a1.id,
        assigned_to_id=test_user_owner.id,
        title="Alpha Enterprise SaaS",
        value=50000.0,
        status=DealStatus.OPEN.value,
        win_probability=50,
        expected_close_date=base_time + timedelta(days=10),
        created_at=base_time + timedelta(days=1),
        updated_at=base_time + timedelta(days=1),
    )
    # D2: Beta Hardware Expansion
    deal_2 = Deal(
        id="30000000-0000-0000-0000-000000000002",
        organization_id=test_org.id,
        pipeline_id=pipe_1_id,
        stage_id=s2_id,
        contact_id=cont_a2.id,
        company_id=comp_a2.id,
        assigned_to_id=test_user_member.id,
        title="Beta Hardware Expansion",
        value=120000.0,
        status=DealStatus.WON.value,
        win_probability=100,
        expected_close_date=base_time + timedelta(days=30),
        created_at=base_time + timedelta(days=2),
        updated_at=base_time + timedelta(days=5),
    )
    # D3: Gamma Security Audit (tied value with D5: 20000.0, id 003 < 005)
    deal_3 = Deal(
        id="30000000-0000-0000-0000-000000000003",
        organization_id=test_org.id,
        pipeline_id=pipe_2_id,
        stage_id=s3_id,
        contact_id=cont_a1.id,
        company_id=comp_a1.id,
        assigned_to_id=test_user_owner.id,
        title="Gamma Security Audit",
        value=20000.0,
        status=DealStatus.LOST.value,
        win_probability=0,
        expected_close_date=base_time + timedelta(days=5),
        created_at=base_time + timedelta(days=3),
        updated_at=base_time + timedelta(days=4),
    )
    # D4: Delta Cloud Hosting
    deal_4 = Deal(
        id="30000000-0000-0000-0000-000000000004",
        organization_id=test_org.id,
        pipeline_id=pipe_2_id,
        stage_id=s4_id,
        contact_id=cont_a2.id,
        company_id=comp_a2.id,
        assigned_to_id=test_user_member.id,
        title="Delta Cloud Hosting",
        value=75000.0,
        status=DealStatus.OPEN.value,
        win_probability=80,
        expected_close_date=base_time + timedelta(days=20),
        created_at=base_time + timedelta(days=4),
        updated_at=base_time + timedelta(days=2),
    )
    # D5: Epsilon Consulting (tied value with D3: 20000.0, id 005 > 003)
    deal_5 = Deal(
        id="30000000-0000-0000-0000-000000000005",
        organization_id=test_org.id,
        pipeline_id=pipe_1_id,
        stage_id=s1_id,
        contact_id=None,
        company_id=None,
        assigned_to_id=test_user_owner.id,
        title="Epsilon Consulting",
        value=20000.0,
        status=DealStatus.OPEN.value,
        win_probability=50,
        expected_close_date=None,
        created_at=base_time + timedelta(days=5),
        updated_at=base_time + timedelta(days=3),
    )
    db_session.add_all([deal_1, deal_2, deal_3, deal_4, deal_5])
    await db_session.commit()

    token_b = create_access_token(user_b.id, org_b.id, user_b.role)

    return {
        "org_b": org_b,
        "user_b": user_b,
        "token_b": token_b,
        "pipe_1_id": pipe_1_id,
        "pipe_2_id": pipe_2_id,
        "pipe_b_id": pipe_b.id,
        "s1_id": s1_id,
        "s2_id": s2_id,
        "s3_id": s3_id,
        "s4_id": s4_id,
        "s_b_id": stage_b.id,
        "comp_a1_id": comp_a1.id,
        "comp_a2_id": comp_a2.id,
        "comp_b_id": comp_b.id,
        "cont_a1_id": cont_a1.id,
        "cont_a2_id": cont_a2.id,
        "cont_b_id": contact_b.id,
        "deal_ids": [deal_1.id, deal_2.id, deal_3.id, deal_4.id, deal_5.id],
    }


# ============================================================================
# FILTERING TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_deals_filter_by_pipeline(client: AsyncClient, auth_headers_owner: dict, seed_deals_data):
    """Filter deals by pipeline_id."""
    p1 = seed_deals_data["pipe_1_id"]
    p2 = seed_deals_data["pipe_2_id"]

    # Pipe 1 deals: D1, D2, D5
    resp1 = await client.get(f"/api/v1/deals?pipeline_id={p1}", headers=auth_headers_owner)
    assert resp1.status_code == 200
    titles1 = [d["title"] for d in resp1.json()]
    assert sorted(titles1) == ["Alpha Enterprise SaaS", "Beta Hardware Expansion", "Epsilon Consulting"]

    # Pipe 2 deals: D3, D4
    resp2 = await client.get(f"/api/v1/deals?pipeline_id={p2}", headers=auth_headers_owner)
    assert resp2.status_code == 200
    titles2 = [d["title"] for d in resp2.json()]
    assert sorted(titles2) == ["Delta Cloud Hosting", "Gamma Security Audit"]


@pytest.mark.asyncio
async def test_deals_filter_by_stage(client: AsyncClient, auth_headers_owner: dict, seed_deals_data):
    """Filter deals by stage_id."""
    s1 = seed_deals_data["s1_id"]
    s2 = seed_deals_data["s2_id"]

    resp = await client.get(f"/api/v1/deals?stage_id={s1}", headers=auth_headers_owner)
    assert resp.status_code == 200
    titles = [d["title"] for d in resp.json()]
    assert sorted(titles) == ["Alpha Enterprise SaaS", "Epsilon Consulting"]

    resp2 = await client.get(f"/api/v1/deals?stage_id={s2}", headers=auth_headers_owner)
    assert resp2.status_code == 200
    assert [d["title"] for d in resp2.json()] == ["Beta Hardware Expansion"]


@pytest.mark.asyncio
async def test_deals_filter_by_status(client: AsyncClient, auth_headers_owner: dict, seed_deals_data):
    """Filter deals by status (OPEN, WON, LOST) and check case-insensitivity."""
    # OPEN: D1, D4, D5
    resp_open = await client.get("/api/v1/deals?status=open", headers=auth_headers_owner)
    assert resp_open.status_code == 200
    assert sorted(d["title"] for d in resp_open.json()) == [
        "Alpha Enterprise SaaS",
        "Delta Cloud Hosting",
        "Epsilon Consulting",
    ]

    # WON: D2
    resp_won = await client.get("/api/v1/deals?status=WON", headers=auth_headers_owner)
    assert resp_won.status_code == 200
    assert [d["title"] for d in resp_won.json()] == ["Beta Hardware Expansion"]

    # LOST: D3
    resp_lost = await client.get("/api/v1/deals?status= lost ", headers=auth_headers_owner)
    assert resp_lost.status_code == 200
    assert [d["title"] for d in resp_lost.json()] == ["Gamma Security Audit"]


@pytest.mark.asyncio
async def test_deals_filter_by_assigned_to(
    client: AsyncClient,
    auth_headers_owner: dict,
    test_user_owner: User,
    test_user_member: User,
    seed_deals_data,
):
    """Filter deals by salesperson assigned_to_id."""
    # Owner: D1, D3, D5
    resp_owner = await client.get(f"/api/v1/deals?assigned_to_id={test_user_owner.id}", headers=auth_headers_owner)
    assert resp_owner.status_code == 200
    assert sorted(d["title"] for d in resp_owner.json()) == [
        "Alpha Enterprise SaaS",
        "Epsilon Consulting",
        "Gamma Security Audit",
    ]

    # Member: D2, D4
    resp_member = await client.get(f"/api/v1/deals?assigned_to_id={test_user_member.id}", headers=auth_headers_owner)
    assert resp_member.status_code == 200
    assert sorted(d["title"] for d in resp_member.json()) == [
        "Beta Hardware Expansion",
        "Delta Cloud Hosting",
    ]


@pytest.mark.asyncio
async def test_deals_filter_by_contact_and_company(client: AsyncClient, auth_headers_owner: dict, seed_deals_data):
    """Filter deals by contact_id and company_id."""
    c1 = seed_deals_data["cont_a1_id"]
    comp1 = seed_deals_data["comp_a1_id"]

    # Contact 1: D1, D3
    resp_cont = await client.get(f"/api/v1/deals?contact_id={c1}", headers=auth_headers_owner)
    assert resp_cont.status_code == 200
    assert sorted(d["title"] for d in resp_cont.json()) == ["Alpha Enterprise SaaS", "Gamma Security Audit"]

    # Company 1: D1, D3
    resp_comp = await client.get(f"/api/v1/deals?company_id={comp1}", headers=auth_headers_owner)
    assert resp_comp.status_code == 200
    assert sorted(d["title"] for d in resp_comp.json()) == ["Alpha Enterprise SaaS", "Gamma Security Audit"]


@pytest.mark.asyncio
async def test_deals_search_by_title(client: AsyncClient, auth_headers_owner: dict, seed_deals_data):
    """Search deals case-insensitively by title substring."""
    resp = await client.get("/api/v1/deals?search=CLOUD", headers=auth_headers_owner)
    assert resp.status_code == 200
    assert [d["title"] for d in resp.json()] == ["Delta Cloud Hosting"]

    resp2 = await client.get("/api/v1/deals?search=consulting", headers=auth_headers_owner)
    assert resp2.status_code == 200
    assert [d["title"] for d in resp2.json()] == ["Epsilon Consulting"]


@pytest.mark.asyncio
async def test_deals_combined_filters(
    client: AsyncClient,
    auth_headers_owner: dict,
    test_user_owner: User,
    seed_deals_data,
):
    """Combine multiple filters with AND logic."""
    p1 = seed_deals_data["pipe_1_id"]
    comp1 = seed_deals_data["comp_a1_id"]

    # pipeline 1 + status OPEN + assigned to owner -> D1, D5
    resp = await client.get(
        f"/api/v1/deals?pipeline_id={p1}&status=OPEN&assigned_to_id={test_user_owner.id}",
        headers=auth_headers_owner,
    )
    assert resp.status_code == 200
    assert sorted(d["title"] for d in resp.json()) == ["Alpha Enterprise SaaS", "Epsilon Consulting"]

    # Add company_id -> only D1 matches (D5 has no company)
    resp2 = await client.get(
        f"/api/v1/deals?pipeline_id={p1}&status=OPEN&assigned_to_id={test_user_owner.id}&company_id={comp1}",
        headers=auth_headers_owner,
    )
    assert resp2.status_code == 200
    assert [d["title"] for d in resp2.json()] == ["Alpha Enterprise SaaS"]

    # Non-matching combination returns empty list
    resp3 = await client.get(
        f"/api/v1/deals?pipeline_id={p1}&status=LOST",
        headers=auth_headers_owner,
    )
    assert resp3.status_code == 200
    assert resp3.json() == []


@pytest.mark.asyncio
async def test_deals_filter_sanitization_and_validation(client: AsyncClient, auth_headers_owner: dict, seed_deals_data):
    """Whitespace/empty filters are ignored; invalid status returns HTTP 400."""
    # Empty / whitespace filters return all 5 deals in Org A
    resp = await client.get("/api/v1/deals?pipeline_id=  &search=  &company_id=", headers=auth_headers_owner)
    assert resp.status_code == 200
    assert len(resp.json()) == 5

    # Invalid status returns HTTP 400
    resp_inv = await client.get("/api/v1/deals?status=IN_PROGRESS", headers=auth_headers_owner)
    assert resp_inv.status_code == 400
    assert "Invalid deal status" in resp_inv.json()["error"]["message"]


# ============================================================================
# SORTING TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_deals_sorting_by_all_fields(client: AsyncClient, auth_headers_owner: dict, seed_deals_data):
    """Test sorting by title, value, status, created_at, updated_at, expected_close_date."""
    # 1. title: Alpha, Beta, Delta, Epsilon, Gamma
    resp = await client.get("/api/v1/deals?sort_by=title&sort_order=asc", headers=auth_headers_owner)
    assert resp.status_code == 200
    assert [d["title"] for d in resp.json()] == [
        "Alpha Enterprise SaaS",
        "Beta Hardware Expansion",
        "Delta Cloud Hosting",
        "Epsilon Consulting",
        "Gamma Security Audit",
    ]

    resp = await client.get("/api/v1/deals?sort_by=title&sort_order=desc", headers=auth_headers_owner)
    assert resp.status_code == 200
    assert [d["title"] for d in resp.json()] == [
        "Gamma Security Audit",
        "Epsilon Consulting",
        "Delta Cloud Hosting",
        "Beta Hardware Expansion",
        "Alpha Enterprise SaaS",
    ]

    # 2. value:
    # Values: 20000 (D3, D5), 50000 (D1), 75000 (D4), 120000 (D2)
    # Tied 20000 broken by id.asc() -> D3 id ...0003 < D5 id ...0005
    resp = await client.get("/api/v1/deals?sort_by=value&sort_order=asc", headers=auth_headers_owner)
    assert resp.status_code == 200
    assert [d["title"] for d in resp.json()] == [
        "Gamma Security Audit",
        "Epsilon Consulting",
        "Alpha Enterprise SaaS",
        "Delta Cloud Hosting",
        "Beta Hardware Expansion",
    ]

    resp = await client.get("/api/v1/deals?sort_by=value&sort_order=desc", headers=auth_headers_owner)
    assert resp.status_code == 200
    # Values descending: 120000 (D2), 75000 (D4), 50000 (D1), 20000 (D3 id 003 < D5 id 005)
    assert [d["title"] for d in resp.json()] == [
        "Beta Hardware Expansion",
        "Delta Cloud Hosting",
        "Alpha Enterprise SaaS",
        "Gamma Security Audit",
        "Epsilon Consulting",
    ]

    # 3. status:
    # LOST (D3), OPEN (D1 id 001, D4 id 004, D5 id 005), WON (D2)
    resp = await client.get("/api/v1/deals?sort_by=status&sort_order=asc", headers=auth_headers_owner)
    assert resp.status_code == 200
    assert [d["title"] for d in resp.json()] == [
        "Gamma Security Audit",
        "Alpha Enterprise SaaS",
        "Delta Cloud Hosting",
        "Epsilon Consulting",
        "Beta Hardware Expansion",
    ]

    resp = await client.get("/api/v1/deals?sort_by=status&sort_order=desc", headers=auth_headers_owner)
    assert resp.status_code == 200
    assert [d["title"] for d in resp.json()] == [
        "Beta Hardware Expansion",
        "Alpha Enterprise SaaS",
        "Delta Cloud Hosting",
        "Epsilon Consulting",
        "Gamma Security Audit",
    ]

    # 4. created_at:
    # D1 (day 1), D2 (day 2), D3 (day 3), D4 (day 4), D5 (day 5)
    resp = await client.get("/api/v1/deals?sort_by=created_at&sort_order=asc", headers=auth_headers_owner)
    assert resp.status_code == 200
    assert [d["title"] for d in resp.json()] == [
        "Alpha Enterprise SaaS",
        "Beta Hardware Expansion",
        "Gamma Security Audit",
        "Delta Cloud Hosting",
        "Epsilon Consulting",
    ]

    resp = await client.get("/api/v1/deals?sort_by=created_at&sort_order=desc", headers=auth_headers_owner)
    assert resp.status_code == 200
    assert [d["title"] for d in resp.json()] == [
        "Epsilon Consulting",
        "Delta Cloud Hosting",
        "Gamma Security Audit",
        "Beta Hardware Expansion",
        "Alpha Enterprise SaaS",
    ]

    # 5. updated_at:
    # D1 (day 1), D4 (day 2), D5 (day 3), D3 (day 4), D2 (day 5)
    resp = await client.get("/api/v1/deals?sort_by=updated_at&sort_order=asc", headers=auth_headers_owner)
    assert resp.status_code == 200
    assert [d["title"] for d in resp.json()] == [
        "Alpha Enterprise SaaS",
        "Delta Cloud Hosting",
        "Epsilon Consulting",
        "Gamma Security Audit",
        "Beta Hardware Expansion",
    ]

    resp = await client.get("/api/v1/deals?sort_by=updated_at&sort_order=desc", headers=auth_headers_owner)
    assert resp.status_code == 200
    assert [d["title"] for d in resp.json()] == [
        "Beta Hardware Expansion",
        "Gamma Security Audit",
        "Epsilon Consulting",
        "Delta Cloud Hosting",
        "Alpha Enterprise SaaS",
    ]


@pytest.mark.asyncio
async def test_deals_sorting_fallbacks(client: AsyncClient, auth_headers_owner: dict, seed_deals_data):
    """Test sort fallbacks when sort_by or sort_order is omitted."""
    # 1. No sort parameters -> defaults to created_at DESC, id ASC
    resp = await client.get("/api/v1/deals", headers=auth_headers_owner)
    assert resp.status_code == 200
    assert [d["title"] for d in resp.json()] == [
        "Epsilon Consulting",
        "Delta Cloud Hosting",
        "Gamma Security Audit",
        "Beta Hardware Expansion",
        "Alpha Enterprise SaaS",
    ]

    # 2. sort_by=title without sort_order -> defaults to asc
    resp = await client.get("/api/v1/deals?sort_by=title", headers=auth_headers_owner)
    assert resp.status_code == 200
    assert [d["title"] for d in resp.json()][0] == "Alpha Enterprise SaaS"

    # 3. sort_by=created_at without sort_order -> defaults to desc
    resp = await client.get("/api/v1/deals?sort_by=created_at", headers=auth_headers_owner)
    assert resp.status_code == 200
    assert [d["title"] for d in resp.json()][0] == "Epsilon Consulting"

    # 4. sort_by=updated_at without sort_order -> defaults to desc
    resp = await client.get("/api/v1/deals?sort_by=updated_at", headers=auth_headers_owner)
    assert resp.status_code == 200
    assert [d["title"] for d in resp.json()][0] == "Beta Hardware Expansion"

    # 5. sort_order=asc without sort_by -> applies asc to default column (created_at ASC)
    resp = await client.get("/api/v1/deals?sort_order=asc", headers=auth_headers_owner)
    assert resp.status_code == 200
    assert [d["title"] for d in resp.json()][0] == "Alpha Enterprise SaaS"

    # 6. sort_order=desc without sort_by -> applies desc to default column (created_at DESC)
    resp = await client.get("/api/v1/deals?sort_order=desc", headers=auth_headers_owner)
    assert resp.status_code == 200
    assert [d["title"] for d in resp.json()][0] == "Epsilon Consulting"


@pytest.mark.asyncio
async def test_deals_invalid_sort(client: AsyncClient, auth_headers_owner: dict, seed_deals_data):
    """Test sorting validation failures (HTTP 400)."""
    # Unsupported sort_by field
    resp = await client.get("/api/v1/deals?sort_by=notes", headers=auth_headers_owner)
    assert resp.status_code == 400
    assert "Invalid sort field 'notes'" in resp.json()["error"]["message"]

    # Unsupported sort_order direction
    resp = await client.get("/api/v1/deals?sort_order=backwards", headers=auth_headers_owner)
    assert resp.status_code == 400
    assert "Invalid sort order" in resp.json()["error"]["message"]


# ============================================================================
# PAGINATION TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_deals_pagination(client: AsyncClient, auth_headers_owner: dict, seed_deals_data):
    """Test limit, offset, and non-overlapping pagination with deterministic secondary tie-breaking."""
    # Page 1: limit 2, offset 0 (sorted by title ASC: Alpha, Beta)
    resp1 = await client.get("/api/v1/deals?sort_by=title&sort_order=asc&limit=2&offset=0", headers=auth_headers_owner)
    assert resp1.status_code == 200
    assert [d["title"] for d in resp1.json()] == ["Alpha Enterprise SaaS", "Beta Hardware Expansion"]

    # Page 2: limit 2, offset 2 (Delta, Epsilon)
    resp2 = await client.get("/api/v1/deals?sort_by=title&sort_order=asc&limit=2&offset=2", headers=auth_headers_owner)
    assert resp2.status_code == 200
    assert [d["title"] for d in resp2.json()] == ["Delta Cloud Hosting", "Epsilon Consulting"]

    # Page 3: limit 2, offset 4 (Gamma)
    resp3 = await client.get("/api/v1/deals?sort_by=title&sort_order=asc&limit=2&offset=4", headers=auth_headers_owner)
    assert resp3.status_code == 200
    assert [d["title"] for d in resp3.json()] == ["Gamma Security Audit"]

    # Page 4: offset beyond total count returns empty list
    resp4 = await client.get("/api/v1/deals?sort_by=title&sort_order=asc&limit=2&offset=10", headers=auth_headers_owner)
    assert resp4.status_code == 200
    assert resp4.json() == []

    # Limit validation: limit < 1 returns 422
    resp_inv = await client.get("/api/v1/deals?limit=0", headers=auth_headers_owner)
    assert resp_inv.status_code == 422

    # Limit validation: limit > 500 returns 422
    resp_inv2 = await client.get("/api/v1/deals?limit=501", headers=auth_headers_owner)
    assert resp_inv2.status_code == 422


# ============================================================================
# TENANT ISOLATION TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_deals_tenant_isolation(client: AsyncClient, auth_headers_owner: dict, seed_deals_data):
    """Org A never sees Org B deals, and filtering with Org B foreign entity IDs returns empty list."""
    # 1. Org A list endpoint only contains Org A deals
    resp = await client.get("/api/v1/deals", headers=auth_headers_owner)
    assert resp.status_code == 200
    titles = [d["title"] for d in resp.json()]
    assert len(titles) == 5
    assert "Alpha Foreign Deal In Org B" not in titles

    # 2. Org A filtering with Org B pipeline_id returns []
    pipe_b = seed_deals_data["pipe_b_id"]
    resp_pipe = await client.get(f"/api/v1/deals?pipeline_id={pipe_b}", headers=auth_headers_owner)
    assert resp_pipe.status_code == 200
    assert resp_pipe.json() == []

    # 3. Org A filtering with Org B stage_id returns []
    s_b = seed_deals_data["s_b_id"]
    resp_stage = await client.get(f"/api/v1/deals?stage_id={s_b}", headers=auth_headers_owner)
    assert resp_stage.status_code == 200
    assert resp_stage.json() == []

    # 4. Org A filtering with Org B contact_id returns []
    cont_b = seed_deals_data["cont_b_id"]
    resp_cont = await client.get(f"/api/v1/deals?contact_id={cont_b}", headers=auth_headers_owner)
    assert resp_cont.status_code == 200
    assert resp_cont.json() == []

    # 5. Org A filtering with Org B company_id returns []
    comp_b = seed_deals_data["comp_b_id"]
    resp_comp = await client.get(f"/api/v1/deals?company_id={comp_b}", headers=auth_headers_owner)
    assert resp_comp.status_code == 200
    assert resp_comp.json() == []

    # 6. Org A filtering with Org B assigned_to_id returns []
    user_b = seed_deals_data["user_b"]
    resp_user = await client.get(f"/api/v1/deals?assigned_to_id={user_b.id}", headers=auth_headers_owner)
    assert resp_user.status_code == 200
    assert resp_user.json() == []

    # 7. Org B user only sees Org B deal
    token_b = seed_deals_data["token_b"]
    headers_b = {"Authorization": f"Bearer {token_b}"}
    resp_b = await client.get("/api/v1/deals", headers=headers_b)
    assert resp_b.status_code == 200
    data_b = resp_b.json()
    assert len(data_b) == 1
    assert data_b[0]["title"] == "Alpha Foreign Deal In Org B"
