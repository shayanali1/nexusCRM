import pytest
import pytest_asyncio
from datetime import datetime, timezone, timedelta
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.security import create_access_token, hash_password
from app.modules.calendar.models import CalendarEvent
from app.modules.companies.models import Company
from app.modules.contacts.models import Contact
from app.modules.deals.models import Deal
from app.modules.leads.models import Lead
from app.modules.organizations.models import Organization
from app.modules.pipelines.models import Pipeline, PipelineStage
from app.modules.users.models import User


@pytest_asyncio.fixture(scope="function")
async def seed_calendar_test_data(
    db_session: AsyncSession,
    test_org: Organization,
    test_user_owner: User,
    test_user_member: User,
):
    """Seed comprehensive test entities for calendar module across Org A and Org B."""
    base_time = datetime(2026, 9, 1, 10, 0, 0, tzinfo=timezone.utc)

    # 1. Org A entities
    lead_a = Lead(
        organization_id=test_org.id,
        title="Alpha Corp Lead",
        assigned_to_id=test_user_owner.id,
        status="NEW",
    )
    db_session.add(lead_a)

    company_a = Company(
        organization_id=test_org.id,
        name="Alpha Dynamics",
    )
    db_session.add(company_a)
    await db_session.flush()

    contact_a = Contact(
        organization_id=test_org.id,
        company_id=company_a.id,
        first_name="Alice",
        last_name="Alpha",
        email="alice@alpha.com",
    )
    db_session.add(contact_a)

    pipe_a = Pipeline(
        organization_id=test_org.id,
        name="Alpha Pipeline",
        is_default=True,
    )
    db_session.add(pipe_a)
    await db_session.flush()

    stage_a = PipelineStage(
        organization_id=test_org.id,
        pipeline_id=pipe_a.id,
        name="Discovery",
        order=1,
        win_probability=25,
    )
    db_session.add(stage_a)
    await db_session.flush()

    deal_a = Deal(
        organization_id=test_org.id,
        pipeline_id=pipe_a.id,
        stage_id=stage_a.id,
        contact_id=contact_a.id,
        company_id=company_a.id,
        title="Alpha Enterprise Deal",
        value=75000.0,
    )
    db_session.add(deal_a)

    inactive_user_a = User(
        organization_id=test_org.id,
        email="inactive@alpha.com",
        hashed_password=hash_password("password123"),
        first_name="Inactive",
        last_name="User",
        role="MEMBER",
        is_active=False,
    )
    db_session.add(inactive_user_a)
    await db_session.flush()

    # Event A1: linked to lead, contact, deal, owner
    event_a1 = CalendarEvent(
        organization_id=test_org.id,
        user_id=test_user_owner.id,
        lead_id=lead_a.id,
        contact_id=contact_a.id,
        deal_id=deal_a.id,
        title="Quarterly Strategy Meeting",
        description="Q3 Strategic planning session",
        location="Boardroom A",
        meeting_link="https://meet.google.com/qtr-strat",
        start_time=base_time + timedelta(days=1),
        end_time=base_time + timedelta(days=1, hours=1),
        provider="google",
    )
    # Event A2: linked to member
    event_a2 = CalendarEvent(
        organization_id=test_org.id,
        user_id=test_user_member.id,
        title="Product Demo",
        description="Showcasing new CRM features",
        location="Virtual / Zoom",
        meeting_link="https://zoom.us/j/demo123",
        start_time=base_time + timedelta(days=2),
        end_time=base_time + timedelta(days=2, minutes=45),
        provider="google",
    )
    # Event A3: linked to owner
    event_a3 = CalendarEvent(
        organization_id=test_org.id,
        user_id=test_user_owner.id,
        title="Annual Budget Review",
        description="Financial review and budget allocation for next FY",
        location="Conference Room B",
        meeting_link="https://meet.google.com/budget-rev",
        start_time=base_time + timedelta(days=3),
        end_time=base_time + timedelta(days=3, hours=2),
        provider="google",
    )
    db_session.add_all([event_a1, event_a2, event_a3])

    # 2. Org B entities (different tenant)
    org_b = Organization(
        name="Org Beta",
        slug="org-beta",
        is_active=True,
    )
    db_session.add(org_b)
    await db_session.flush()

    user_b = User(
        organization_id=org_b.id,
        email="owner@beta.com",
        hashed_password=hash_password("password123"),
        first_name="Beta",
        last_name="Owner",
        role="OWNER",
        is_active=True,
    )
    db_session.add(user_b)
    await db_session.flush()

    lead_b = Lead(
        organization_id=org_b.id,
        title="Beta Lead Corp",
        assigned_to_id=user_b.id,
        status="NEW",
    )
    db_session.add(lead_b)

    contact_b = Contact(
        organization_id=org_b.id,
        first_name="Bob",
        last_name="Beta",
        email="bob@beta.com",
    )
    db_session.add(contact_b)

    pipe_b = Pipeline(
        organization_id=org_b.id,
        name="Beta Pipeline",
        is_default=True,
    )
    db_session.add(pipe_b)
    await db_session.flush()

    stage_b = PipelineStage(
        organization_id=org_b.id,
        pipeline_id=pipe_b.id,
        name="Beta Discovery",
        order=1,
        win_probability=50,
    )
    db_session.add(stage_b)
    await db_session.flush()

    deal_b = Deal(
        organization_id=org_b.id,
        pipeline_id=pipe_b.id,
        stage_id=stage_b.id,
        contact_id=contact_b.id,
        title="Beta Deal",
        value=100000.0,
    )
    db_session.add(deal_b)
    await db_session.flush()

    event_b = CalendarEvent(
        organization_id=org_b.id,
        user_id=user_b.id,
        lead_id=lead_b.id,
        contact_id=contact_b.id,
        deal_id=deal_b.id,
        title="Beta Secret Sync",
        description="Confidential sync in Org B",
        location="Room 404",
        start_time=base_time + timedelta(days=1),
        end_time=base_time + timedelta(days=1, minutes=30),
        provider="google",
    )
    db_session.add(event_b)

    await db_session.commit()
    await db_session.refresh(lead_a)
    await db_session.refresh(contact_a)
    await db_session.refresh(deal_a)
    await db_session.refresh(inactive_user_a)
    await db_session.refresh(event_a1)
    await db_session.refresh(event_a2)
    await db_session.refresh(event_a3)
    await db_session.refresh(org_b)
    await db_session.refresh(user_b)
    await db_session.refresh(lead_b)
    await db_session.refresh(contact_b)
    await db_session.refresh(deal_b)
    await db_session.refresh(event_b)

    token_b = create_access_token(user_b.id, org_b.id, user_b.role)
    auth_headers_b = {"Authorization": f"Bearer {token_b}"}

    return {
        "base_time": base_time,
        "lead_a": lead_a,
        "contact_a": contact_a,
        "deal_a": deal_a,
        "inactive_user_a": inactive_user_a,
        "event_a1": event_a1,
        "event_a2": event_a2,
        "event_a3": event_a3,
        "org_b": org_b,
        "user_b": user_b,
        "lead_b": lead_b,
        "contact_b": contact_b,
        "deal_b": deal_b,
        "event_b": event_b,
        "auth_headers_b": auth_headers_b,
    }


# ==============================================================================
# 1. Full CRUD Lifecycle & Lead Title Hydration
# ==============================================================================


@pytest.mark.asyncio
async def test_calendar_crud_lifecycle_and_lead_title(
    client: AsyncClient,
    auth_headers_owner: dict,
    test_user_owner: User,
    seed_calendar_test_data: dict,
):
    """Test full CRUD lifecycle, user_id default, and lead_title hydration."""
    data = seed_calendar_test_data
    lead = data["lead_a"]
    contact = data["contact_a"]
    deal = data["deal_a"]
    start = datetime(2026, 9, 10, 14, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 9, 10, 15, 0, 0, tzinfo=timezone.utc)

    # 1. Create event without user_id -> defaults to current user
    create_payload = {
        "title": "Onboarding Kickoff",
        "description": "Initial onboarding for Alpha Corp",
        "lead_id": lead.id,
        "contact_id": contact.id,
        "deal_id": deal.id,
        "location": "Room 202",
        "meeting_link": "https://meet.google.com/kickoff",
        "start_time": start.isoformat(),
        "end_time": end.isoformat(),
        "provider": "google",
    }
    res = await client.post("/api/v1/calendar", json=create_payload, headers=auth_headers_owner)
    assert res.status_code == 201, res.text
    created = res.json()
    event_id = created["id"]
    assert created["title"] == "Onboarding Kickoff"
    assert created["user_id"] == test_user_owner.id
    assert created["lead_id"] == lead.id
    assert created["lead_title"] == "Alpha Corp Lead"
    assert created["contact_id"] == contact.id
    assert created["deal_id"] == deal.id
    assert created["location"] == "Room 202"

    # 2. Get event by ID
    res = await client.get(f"/api/v1/calendar/{event_id}", headers=auth_headers_owner)
    assert res.status_code == 200
    fetched = res.json()
    assert fetched["id"] == event_id
    assert fetched["lead_title"] == "Alpha Corp Lead"

    # 3. Patch event
    patch_payload = {
        "title": "Updated Onboarding Kickoff",
        "location": "Executive Boardroom",
        "meeting_link": "https://meet.google.com/kickoff-updated",
    }
    res = await client.patch(f"/api/v1/calendar/{event_id}", json=patch_payload, headers=auth_headers_owner)
    assert res.status_code == 200
    updated = res.json()
    assert updated["title"] == "Updated Onboarding Kickoff"
    assert updated["location"] == "Executive Boardroom"
    assert updated["meeting_link"] == "https://meet.google.com/kickoff-updated"
    assert updated["lead_title"] == "Alpha Corp Lead"

    # 4. Delete event
    res = await client.delete(f"/api/v1/calendar/{event_id}", headers=auth_headers_owner)
    assert res.status_code == 204

    # 5. Get after delete -> 404
    res = await client.get(f"/api/v1/calendar/{event_id}", headers=auth_headers_owner)
    assert res.status_code == 404

    # 6. Delete again -> 404
    res = await client.delete(f"/api/v1/calendar/{event_id}", headers=auth_headers_owner)
    assert res.status_code == 404


# ==============================================================================
# 2. Time Order Validation
# ==============================================================================


@pytest.mark.asyncio
async def test_calendar_time_order_validation(
    client: AsyncClient,
    auth_headers_owner: dict,
    seed_calendar_test_data: dict,
):
    """Test rejection of invalid end_time <= start_time on creation and update."""
    data = seed_calendar_test_data
    event = data["event_a1"]
    base = datetime(2026, 9, 15, 10, 0, 0, tzinfo=timezone.utc)

    # 1. Create with end_time < start_time -> 400
    payload_inverted = {
        "title": "Inverted Time Event",
        "start_time": (base + timedelta(hours=2)).isoformat(),
        "end_time": base.isoformat(),
    }
    res = await client.post("/api/v1/calendar", json=payload_inverted, headers=auth_headers_owner)
    assert res.status_code == 400
    assert "End time must be after start time." in res.text

    # 2. Create with end_time == start_time -> 400
    payload_equal = {
        "title": "Equal Time Event",
        "start_time": base.isoformat(),
        "end_time": base.isoformat(),
    }
    res = await client.post("/api/v1/calendar", json=payload_equal, headers=auth_headers_owner)
    assert res.status_code == 400
    assert "End time must be after start time." in res.text

    # 3. Patch existing event: update only end_time earlier than existing start_time -> 400
    # event.start_time is 2026-09-02 10:00:00
    early_end = (datetime(2026, 9, 2, 9, 0, 0, tzinfo=timezone.utc)).isoformat()
    res = await client.patch(
        f"/api/v1/calendar/{event.id}",
        json={"end_time": early_end},
        headers=auth_headers_owner,
    )
    assert res.status_code == 400
    assert "End time must be after start time." in res.text

    # 4. Patch existing event: update only start_time later than existing end_time -> 400
    # event.end_time is 2026-09-02 11:00:00
    late_start = (datetime(2026, 9, 2, 12, 0, 0, tzinfo=timezone.utc)).isoformat()
    res = await client.patch(
        f"/api/v1/calendar/{event.id}",
        json={"start_time": late_start},
        headers=auth_headers_owner,
    )
    assert res.status_code == 400
    assert "End time must be after start time." in res.text

    # 5. Patch both start_time and end_time inverted -> 400
    res = await client.patch(
        f"/api/v1/calendar/{event.id}",
        json={"start_time": late_start, "end_time": early_end},
        headers=auth_headers_owner,
    )
    assert res.status_code == 400
    assert "End time must be after start time." in res.text

    # 6. Valid patch moving both forward -> 200
    valid_start = (datetime(2026, 9, 2, 14, 0, 0, tzinfo=timezone.utc)).isoformat()
    valid_end = (datetime(2026, 9, 2, 15, 0, 0, tzinfo=timezone.utc)).isoformat()
    res = await client.patch(
        f"/api/v1/calendar/{event.id}",
        json={"start_time": valid_start, "end_time": valid_end},
        headers=auth_headers_owner,
    )
    assert res.status_code == 200


# ==============================================================================
# 3. Cross-Tenant Relationship Validation
# ==============================================================================


@pytest.mark.asyncio
async def test_calendar_cross_tenant_relationship_validation(
    client: AsyncClient,
    auth_headers_owner: dict,
    seed_calendar_test_data: dict,
):
    """Test that referencing foreign-tenant or inactive entities yields 404."""
    data = seed_calendar_test_data
    event = data["event_a1"]
    lead_b = data["lead_b"]
    contact_b = data["contact_b"]
    deal_b = data["deal_b"]
    user_b = data["user_b"]
    inactive_user = data["inactive_user_a"]

    base_start = (datetime(2026, 9, 20, 10, 0, 0, tzinfo=timezone.utc)).isoformat()
    base_end = (datetime(2026, 9, 20, 11, 0, 0, tzinfo=timezone.utc)).isoformat()

    # 1. Create with Org B lead_id -> 404
    res = await client.post(
        "/api/v1/calendar",
        json={"title": "Test Event", "start_time": base_start, "end_time": base_end, "lead_id": lead_b.id},
        headers=auth_headers_owner,
    )
    assert res.status_code == 404
    assert "Lead not found." in res.text

    # 2. Create with Org B contact_id -> 404
    res = await client.post(
        "/api/v1/calendar",
        json={"title": "Test Event", "start_time": base_start, "end_time": base_end, "contact_id": contact_b.id},
        headers=auth_headers_owner,
    )
    assert res.status_code == 404
    assert "Contact not found." in res.text

    # 3. Create with Org B deal_id -> 404
    res = await client.post(
        "/api/v1/calendar",
        json={"title": "Test Event", "start_time": base_start, "end_time": base_end, "deal_id": deal_b.id},
        headers=auth_headers_owner,
    )
    assert res.status_code == 404
    assert "Deal not found." in res.text

    # 4. Create with Org B user_id -> 404
    res = await client.post(
        "/api/v1/calendar",
        json={"title": "Test Event", "start_time": base_start, "end_time": base_end, "user_id": user_b.id},
        headers=auth_headers_owner,
    )
    assert res.status_code == 404
    assert "User not found." in res.text

    # 5. Create with Org A inactive user -> 404
    res = await client.post(
        "/api/v1/calendar",
        json={"title": "Test Event", "start_time": base_start, "end_time": base_end, "user_id": inactive_user.id},
        headers=auth_headers_owner,
    )
    assert res.status_code == 404
    assert "User not found." in res.text

    # 6. Create with non-existent UUID -> 404
    res = await client.post(
        "/api/v1/calendar",
        json={"title": "Test Event", "start_time": base_start, "end_time": base_end, "lead_id": "00000000-0000-0000-0000-000000000000"},
        headers=auth_headers_owner,
    )
    assert res.status_code == 404

    # 7. Patch existing event with Org B lead_id -> 404
    res = await client.patch(
        f"/api/v1/calendar/{event.id}",
        json={"lead_id": lead_b.id},
        headers=auth_headers_owner,
    )
    assert res.status_code == 404
    assert "Lead not found." in res.text

    # 8. Patch existing event with Org B contact_id -> 404
    res = await client.patch(
        f"/api/v1/calendar/{event.id}",
        json={"contact_id": contact_b.id},
        headers=auth_headers_owner,
    )
    assert res.status_code == 404
    assert "Contact not found." in res.text

    # 9. Patch existing event with Org B deal_id -> 404
    res = await client.patch(
        f"/api/v1/calendar/{event.id}",
        json={"deal_id": deal_b.id},
        headers=auth_headers_owner,
    )
    assert res.status_code == 404
    assert "Deal not found." in res.text

    # 10. Patch existing event with Org B user_id -> 404
    res = await client.patch(
        f"/api/v1/calendar/{event.id}",
        json={"user_id": user_b.id},
        headers=auth_headers_owner,
    )
    assert res.status_code == 404
    assert "User not found." in res.text

    # 11. Patch existing event with inactive user -> 404
    res = await client.patch(
        f"/api/v1/calendar/{event.id}",
        json={"user_id": inactive_user.id},
        headers=auth_headers_owner,
    )
    assert res.status_code == 404
    assert "User not found." in res.text


# ==============================================================================
# 4. Cross-Tenant Event Isolation
# ==============================================================================


@pytest.mark.asyncio
async def test_calendar_cross_tenant_isolation(
    client: AsyncClient,
    auth_headers_owner: dict,
    seed_calendar_test_data: dict,
):
    """Test that events cannot be read, updated, deleted, or listed across organizations."""
    data = seed_calendar_test_data
    event_a = data["event_a1"]
    event_b = data["event_b"]
    auth_headers_b = data["auth_headers_b"]

    # 1. Org A attempts to access Org B event -> 404
    res = await client.get(f"/api/v1/calendar/{event_b.id}", headers=auth_headers_owner)
    assert res.status_code == 404

    res = await client.patch(
        f"/api/v1/calendar/{event_b.id}",
        json={"title": "Hacked Title"},
        headers=auth_headers_owner,
    )
    assert res.status_code == 404

    res = await client.delete(f"/api/v1/calendar/{event_b.id}", headers=auth_headers_owner)
    assert res.status_code == 404

    # 2. Org B attempts to access Org A event -> 404
    res = await client.get(f"/api/v1/calendar/{event_a.id}", headers=auth_headers_b)
    assert res.status_code == 404

    res = await client.patch(
        f"/api/v1/calendar/{event_a.id}",
        json={"title": "Hacked Title"},
        headers=auth_headers_b,
    )
    assert res.status_code == 404

    res = await client.delete(f"/api/v1/calendar/{event_a.id}", headers=auth_headers_b)
    assert res.status_code == 404

    # 3. Org A list -> contains Org A events only
    res = await client.get("/api/v1/calendar", headers=auth_headers_owner)
    assert res.status_code == 200
    ids_a = [e["id"] for e in res.json()]
    assert event_a.id in ids_a
    assert event_b.id not in ids_a

    # 4. Org B list -> contains Org B event only
    res = await client.get("/api/v1/calendar", headers=auth_headers_b)
    assert res.status_code == 200
    ids_b = [e["id"] for e in res.json()]
    assert event_b.id in ids_b
    assert event_a.id not in ids_b


# ==============================================================================
# 5. Filtering, Date-Window / Agenda, Search & Sorting
# ==============================================================================


@pytest.mark.asyncio
async def test_calendar_filtering_date_window_agenda(
    client: AsyncClient,
    auth_headers_owner: dict,
    test_user_member: User,
    seed_calendar_test_data: dict,
):
    """Test relationship filters, agenda date-window boundaries, and inverted date error."""
    data = seed_calendar_test_data
    base = data["base_time"]
    lead = data["lead_a"]
    contact = data["contact_a"]
    deal = data["deal_a"]
    event1 = data["event_a1"]
    event2 = data["event_a2"]

    # 1. Filter by lead_id
    res = await client.get(f"/api/v1/calendar?lead_id={lead.id}", headers=auth_headers_owner)
    assert res.status_code == 200
    items = res.json()
    assert len(items) == 1
    assert items[0]["id"] == event1.id

    # 2. Filter by contact_id
    res = await client.get(f"/api/v1/calendar?contact_id={contact.id}", headers=auth_headers_owner)
    assert res.status_code == 200
    items = res.json()
    assert len(items) == 1
    assert items[0]["id"] == event1.id

    # 3. Filter by deal_id
    res = await client.get(f"/api/v1/calendar?deal_id={deal.id}", headers=auth_headers_owner)
    assert res.status_code == 200
    items = res.json()
    assert len(items) == 1
    assert items[0]["id"] == event1.id

    # 4. Filter by user_id
    res = await client.get(f"/api/v1/calendar?user_id={test_user_member.id}", headers=auth_headers_owner)
    assert res.status_code == 200
    items = res.json()
    assert len(items) == 1
    assert items[0]["id"] == event2.id

    # 5. Date-window filter covering only event2 (Day 2)
    # event1 is Day 1 10:00, event2 is Day 2 10:00, event3 is Day 3 10:00
    window_start = (base + timedelta(days=1, hours=12)).isoformat()
    window_end = (base + timedelta(days=2, hours=12)).isoformat()
    res = await client.get(
        "/api/v1/calendar",
        params={"start_date": window_start, "end_date": window_end},
        headers=auth_headers_owner,
    )
    assert res.status_code == 200
    items = res.json()
    assert len(items) == 1
    assert items[0]["id"] == event2.id

    # 6. Future date window with no events
    future_start = (base + timedelta(days=10)).isoformat()
    future_end = (base + timedelta(days=11)).isoformat()
    res = await client.get(
        "/api/v1/calendar",
        params={"start_date": future_start, "end_date": future_end},
        headers=auth_headers_owner,
    )
    assert res.status_code == 200
    assert len(res.json()) == 0

    # 7. Inverted dates -> 400
    res = await client.get(
        "/api/v1/calendar",
        params={"start_date": window_end, "end_date": window_start},
        headers=auth_headers_owner,
    )
    assert res.status_code == 400
    assert "Start date cannot be after end date." in res.text


@pytest.mark.asyncio
async def test_calendar_search_and_sorting(
    client: AsyncClient,
    auth_headers_owner: dict,
    seed_calendar_test_data: dict,
):
    """Test text search across fields, deterministic sorting, and bad params."""
    data = seed_calendar_test_data
    event1 = data["event_a1"]  # title: Quarterly Strategy Meeting, loc: Boardroom A
    event2 = data["event_a2"]  # title: Product Demo, desc: Showcasing new CRM features
    event3 = data["event_a3"]  # title: Annual Budget Review, desc: Financial review..., loc: Conference Room B

    # 1. Search title
    res = await client.get("/api/v1/calendar?search=Quarterly", headers=auth_headers_owner)
    assert res.status_code == 200
    items = res.json()
    assert len(items) == 1
    assert items[0]["id"] == event1.id

    # 2. Search description
    res = await client.get("/api/v1/calendar?search=budget+allocation", headers=auth_headers_owner)
    assert res.status_code == 200
    items = res.json()
    assert len(items) == 1
    assert items[0]["id"] == event3.id

    # 3. Search location
    res = await client.get("/api/v1/calendar?search=Conference+Room+B", headers=auth_headers_owner)
    assert res.status_code == 200
    items = res.json()
    assert len(items) == 1
    assert items[0]["id"] == event3.id

    # 4. Search no match
    res = await client.get("/api/v1/calendar?search=nonexistent_meeting_xyz", headers=auth_headers_owner)
    assert res.status_code == 200
    assert len(res.json()) == 0

    # 5. Default sort: start_time asc
    res = await client.get("/api/v1/calendar", headers=auth_headers_owner)
    assert res.status_code == 200
    ids = [e["id"] for e in res.json()]
    assert ids == [event1.id, event2.id, event3.id]

    # 6. Sort start_time desc
    res = await client.get("/api/v1/calendar?sort_by=start_time&sort_order=desc", headers=auth_headers_owner)
    assert res.status_code == 200
    ids = [e["id"] for e in res.json()]
    assert ids == [event3.id, event2.id, event1.id]

    # 7. Sort title asc
    # Alphabetical titles: "Annual Budget Review" (event3), "Product Demo" (event2), "Quarterly Strategy Meeting" (event1)
    res = await client.get("/api/v1/calendar?sort_by=title&sort_order=asc", headers=auth_headers_owner)
    assert res.status_code == 200
    ids = [e["id"] for e in res.json()]
    assert ids == [event3.id, event2.id, event1.id]

    # 8. Sort title desc
    res = await client.get("/api/v1/calendar?sort_by=title&sort_order=desc", headers=auth_headers_owner)
    assert res.status_code == 200
    ids = [e["id"] for e in res.json()]
    assert ids == [event1.id, event2.id, event3.id]

    # 9. Invalid sort_by -> 400
    res = await client.get("/api/v1/calendar?sort_by=invalid_column", headers=auth_headers_owner)
    assert res.status_code == 400
    assert "Invalid sort field" in res.text

    # 10. Invalid sort_order -> 400
    res = await client.get("/api/v1/calendar?sort_order=sideways", headers=auth_headers_owner)
    assert res.status_code == 400
    assert "Invalid sort order" in res.text

    # 11. Pagination: limit and offset
    res = await client.get("/api/v1/calendar?limit=2&offset=0", headers=auth_headers_owner)
    assert res.status_code == 200
    assert len(res.json()) == 2
    assert res.json()[0]["id"] == event1.id

    res = await client.get("/api/v1/calendar?limit=2&offset=2", headers=auth_headers_owner)
    assert res.status_code == 200
    assert len(res.json()) == 1
    assert res.json()[0]["id"] == event3.id


# ==============================================================================
# 6. RBAC Permissions & Authentication
# ==============================================================================


@pytest.mark.asyncio
async def test_calendar_rbac_permissions(
    client: AsyncClient,
    auth_headers_owner: dict,
    auth_headers_member: dict,
    seed_calendar_test_data: dict,
):
    """Test RBAC enforcement: unauthenticated (401), member operations, and delete restriction (403)."""
    data = seed_calendar_test_data
    event = data["event_a1"]
    base_start = (datetime(2026, 9, 25, 10, 0, 0, tzinfo=timezone.utc)).isoformat()
    base_end = (datetime(2026, 9, 25, 11, 0, 0, tzinfo=timezone.utc)).isoformat()

    # 1. Unauthenticated -> 401
    res = await client.get("/api/v1/calendar")
    assert res.status_code == 401

    res = await client.post(
        "/api/v1/calendar",
        json={"title": "No Auth Event", "start_time": base_start, "end_time": base_end},
    )
    assert res.status_code == 401

    # 2. Member can list events -> 200
    res = await client.get("/api/v1/calendar", headers=auth_headers_member)
    assert res.status_code == 200

    # 3. Member can create event -> 201
    res = await client.post(
        "/api/v1/calendar",
        json={"title": "Member Sync", "start_time": base_start, "end_time": base_end},
        headers=auth_headers_member,
    )
    assert res.status_code == 201
    created_id = res.json()["id"]

    # 4. Member can update event -> 200
    res = await client.patch(
        f"/api/v1/calendar/{created_id}",
        json={"location": "Huddle Space 1"},
        headers=auth_headers_member,
    )
    assert res.status_code == 200
    assert res.json()["location"] == "Huddle Space 1"

    # 5. Member CANNOT delete event -> 403 Forbidden
    res = await client.delete(f"/api/v1/calendar/{created_id}", headers=auth_headers_member)
    assert res.status_code == 403

    # 6. Owner CAN delete event -> 204
    res = await client.delete(f"/api/v1/calendar/{created_id}", headers=auth_headers_owner)
    assert res.status_code == 204
