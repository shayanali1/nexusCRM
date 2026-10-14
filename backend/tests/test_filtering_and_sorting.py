import pytest
import pytest_asyncio
from datetime import datetime, timezone, timedelta
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.companies.models import Company
from app.modules.contacts.models import Contact
from app.modules.leads.models import Lead, LeadPriority, LeadStatus
from app.modules.organizations.models import Organization
from app.modules.users.models import User


@pytest_asyncio.fixture(scope="function")
async def seed_data(db_session: AsyncSession, test_org: Organization, test_user_owner: User):
    """Seed test contacts, companies, and leads in Org A, plus foreign entities in Org B."""
    # Org B (tenant isolation check)
    org_b = Organization(name="Tenant B", slug="tenant-b", is_active=True)
    db_session.add(org_b)
    await db_session.flush()

    base_time = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    # Companies in Org A
    comp_a1 = Company(
        id="10000000-0000-0000-0000-000000000001",
        organization_id=test_org.id,
        name="Alpha Tech",
        domain="alphatech.io",
        industry="Technology",
        size="51-200",
        city="San Francisco",
        country="USA",
        created_at=base_time + timedelta(days=1),
    )
    comp_a2 = Company(
        id="10000000-0000-0000-0000-000000000002",
        organization_id=test_org.id,
        name="Beta Logistics",
        domain="betalogistics.com",
        industry="Logistics",
        size="201-500",
        city="Chicago",
        country="USA",
        created_at=base_time + timedelta(days=2),
    )
    comp_a3 = Company(
        id="10000000-0000-0000-0000-000000000003",
        organization_id=test_org.id,
        name="Gamma Healthcare",
        domain="gammahealth.org",
        industry="Healthcare",
        size="1-50",
        city="London",
        country="UK",
        created_at=base_time + timedelta(days=3),
    )
    # Company in Org B
    comp_b = Company(
        id="10000000-0000-0000-0000-000000000009",
        organization_id=org_b.id,
        name="Omega Tech",
        domain="omegatech.io",
        industry="Technology",
        size="51-200",
        city="San Francisco",
        country="USA",
        created_at=base_time + timedelta(days=4),
    )
    db_session.add_all([comp_a1, comp_a2, comp_a3, comp_b])
    await db_session.flush()

    # Contacts in Org A
    contact_a1 = Contact(
        id="20000000-0000-0000-0000-000000000001",
        organization_id=test_org.id,
        company_id=comp_a1.id,
        first_name="Alice",
        last_name="Zimmer",
        email="alice.zimmer@alpha.com",
        title="CTO",
        lead_source="Referral",
        created_at=base_time + timedelta(days=1),
    )
    contact_a2 = Contact(
        id="20000000-0000-0000-0000-000000000002",
        organization_id=test_org.id,
        company_id=comp_a2.id,
        first_name="Bob",
        last_name="Adams",
        email="bob.adams@beta.com",
        title="Operations Director",
        lead_source="Inbound",
        created_at=base_time + timedelta(days=2),
    )
    contact_a3 = Contact(
        id="20000000-0000-0000-0000-000000000003",
        organization_id=test_org.id,
        company_id=comp_a3.id,
        first_name="Charlie",
        last_name="Brown",
        email="charlie.brown@gamma.com",
        title="Medical Officer",
        lead_source="Referral",
        created_at=base_time + timedelta(days=3),
    )
    # Contact in Org B
    contact_b = Contact(
        id="20000000-0000-0000-0000-000000000009",
        organization_id=org_b.id,
        company_id=comp_b.id,
        first_name="David",
        last_name="Adams",
        email="david.adams@omega.com",
        title="VP",
        lead_source="Referral",
        created_at=base_time + timedelta(days=4),
    )
    db_session.add_all([contact_a1, contact_a2, contact_a3, contact_b])
    await db_session.flush()

    # Leads in Org A
    lead_a1 = Lead(
        id="30000000-0000-0000-0000-000000000001",
        organization_id=test_org.id,
        contact_id=contact_a1.id,
        company_id=comp_a1.id,
        assigned_to_id=test_user_owner.id,
        title="Alpha Cloud Migration",
        status=LeadStatus.NEW.value,
        source="Website",
        score=85,
        priority=LeadPriority.HIGH.value,
        estimated_value=50000.0,
        created_at=base_time + timedelta(days=1),
    )
    lead_a2 = Lead(
        id="30000000-0000-0000-0000-000000000002",
        organization_id=test_org.id,
        contact_id=contact_a2.id,
        company_id=comp_a2.id,
        assigned_to_id=test_user_owner.id,
        title="Beta Fleet Management",
        status=LeadStatus.CONTACTED.value,
        source="Cold Call",
        score=40,
        priority=LeadPriority.LOW.value,
        estimated_value=15000.0,
        created_at=base_time + timedelta(days=2),
    )
    lead_a3 = Lead(
        id="30000000-0000-0000-0000-000000000003",
        organization_id=test_org.id,
        contact_id=contact_a3.id,
        company_id=comp_a3.id,
        assigned_to_id=None,
        title="Gamma Hospital EHR",
        status=LeadStatus.QUALIFIED.value,
        source="Website",
        score=95,
        priority=LeadPriority.URGENT.value,
        estimated_value=120000.0,
        created_at=base_time + timedelta(days=3),
    )
    # Lead in Org B
    lead_b = Lead(
        id="30000000-0000-0000-0000-000000000009",
        organization_id=org_b.id,
        contact_id=contact_b.id,
        company_id=comp_b.id,
        title="Omega Core Expansion",
        status=LeadStatus.NEW.value,
        source="Website",
        score=90,
        priority=LeadPriority.HIGH.value,
        estimated_value=75000.0,
        created_at=base_time + timedelta(days=4),
    )
    db_session.add_all([lead_a1, lead_a2, lead_a3, lead_b])
    await db_session.commit()

    return {
        "org_b": org_b,
        "companies": [comp_a1, comp_a2, comp_a3],
        "contacts": [contact_a1, contact_a2, contact_a3],
        "leads": [lead_a1, lead_a2, lead_a3],
        "comp_b": comp_b,
        "contact_b": contact_b,
        "lead_b": lead_b,
    }


# ============================================================================
# CONTACTS FILTERING & SORTING TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_contacts_filtering_by_lead_source(client: AsyncClient, auth_headers_owner: dict, seed_data):
    """Test filtering contacts by lead_source with case-insensitivity and whitespace trimming."""
    # Exact case
    resp = await client.get("/api/v1/contacts?lead_source=Referral", headers=auth_headers_owner)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert all(c["lead_source"] == "Referral" for c in data)
    # Tenant isolation check: David Adams from Org B must NOT be included
    assert all(c["first_name"] != "David" for c in data)

    # Case-insensitive
    resp_lower = await client.get("/api/v1/contacts?lead_source=referral", headers=auth_headers_owner)
    assert resp_lower.status_code == 200
    assert len(resp_lower.json()) == 2

    # Whitespace trimming
    resp_spaces = await client.get("/api/v1/contacts?lead_source=%20REFERRAL%20", headers=auth_headers_owner)
    assert resp_spaces.status_code == 200
    assert len(resp_spaces.json()) == 2

    # Empty string should be ignored (returns all contacts of Org A)
    resp_empty = await client.get("/api/v1/contacts?lead_source=", headers=auth_headers_owner)
    assert resp_empty.status_code == 200
    assert len(resp_empty.json()) == 3

    # Non-matching source returns empty list
    resp_none = await client.get("/api/v1/contacts?lead_source=NonExistent", headers=auth_headers_owner)
    assert resp_none.status_code == 200
    assert resp_none.json() == []


@pytest.mark.asyncio
async def test_contacts_combined_filter_and_search(client: AsyncClient, auth_headers_owner: dict, seed_data):
    """Test combining company_id, lead_source, and search on contacts."""
    comp1 = seed_data["companies"][0]
    # Filter by company_id + lead_source
    resp = await client.get(
        f"/api/v1/contacts?company_id={comp1.id}&lead_source=Referral",
        headers=auth_headers_owner,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["last_name"] == "Zimmer"

    # Search + lead_source
    resp = await client.get(
        "/api/v1/contacts?search=Zimmer&lead_source=Referral",
        headers=auth_headers_owner,
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["last_name"] == "Zimmer"

    # Search non-matching + lead_source
    resp = await client.get(
        "/api/v1/contacts?search=NonExistent&lead_source=Referral",
        headers=auth_headers_owner,
    )
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_contacts_default_sorting(client: AsyncClient, auth_headers_owner: dict, seed_data):
    """Test contacts default sorting order: last_name ASC, first_name ASC."""
    resp = await client.get("/api/v1/contacts", headers=auth_headers_owner)
    assert resp.status_code == 200
    last_names = [c["last_name"] for c in resp.json()]
    assert last_names == ["Adams", "Brown", "Zimmer"]


@pytest.mark.asyncio
async def test_contacts_sort_by_all_fields_asc_and_desc(client: AsyncClient, auth_headers_owner: dict, seed_data):
    """Test contacts sorting by every allowed field in both ASC and DESC directions with exact sequence assertions."""
    # 1. last_name: Adams, Brown, Zimmer
    resp = await client.get("/api/v1/contacts?sort_by=last_name&sort_order=asc", headers=auth_headers_owner)
    assert resp.status_code == 200
    assert [c["last_name"] for c in resp.json()] == ["Adams", "Brown", "Zimmer"]

    resp = await client.get("/api/v1/contacts?sort_by=last_name&sort_order=desc", headers=auth_headers_owner)
    assert resp.status_code == 200
    assert [c["last_name"] for c in resp.json()] == ["Zimmer", "Brown", "Adams"]

    # 2. first_name: Alice, Bob, Charlie
    resp = await client.get("/api/v1/contacts?sort_by=first_name&sort_order=asc", headers=auth_headers_owner)
    assert resp.status_code == 200
    assert [c["first_name"] for c in resp.json()] == ["Alice", "Bob", "Charlie"]

    resp = await client.get("/api/v1/contacts?sort_by=first_name&sort_order=desc", headers=auth_headers_owner)
    assert resp.status_code == 200
    assert [c["first_name"] for c in resp.json()] == ["Charlie", "Bob", "Alice"]

    # 3. email: alice.zimmer@alpha.com, bob.adams@beta.com, charlie.brown@gamma.com
    resp = await client.get("/api/v1/contacts?sort_by=email&sort_order=asc", headers=auth_headers_owner)
    assert resp.status_code == 200
    assert [c["email"] for c in resp.json()] == [
        "alice.zimmer@alpha.com",
        "bob.adams@beta.com",
        "charlie.brown@gamma.com",
    ]

    resp = await client.get("/api/v1/contacts?sort_by=email&sort_order=desc", headers=auth_headers_owner)
    assert resp.status_code == 200
    assert [c["email"] for c in resp.json()] == [
        "charlie.brown@gamma.com",
        "bob.adams@beta.com",
        "alice.zimmer@alpha.com",
    ]

    # 4. title: CTO (Zimmer), Medical Officer (Brown), Operations Director (Adams)
    resp = await client.get("/api/v1/contacts?sort_by=title&sort_order=asc", headers=auth_headers_owner)
    assert resp.status_code == 200
    assert [c["title"] for c in resp.json()] == ["CTO", "Medical Officer", "Operations Director"]

    resp = await client.get("/api/v1/contacts?sort_by=title&sort_order=desc", headers=auth_headers_owner)
    assert resp.status_code == 200
    assert [c["title"] for c in resp.json()] == ["Operations Director", "Medical Officer", "CTO"]

    # 5. lead_source: Inbound (Adams), Referral (Zimmer id 001), Referral (Brown id 003)
    # Ties on Referral are broken by Contact.id.asc()
    resp = await client.get("/api/v1/contacts?sort_by=lead_source&sort_order=asc", headers=auth_headers_owner)
    assert resp.status_code == 200
    assert [c["first_name"] for c in resp.json()] == ["Bob", "Alice", "Charlie"]

    resp = await client.get("/api/v1/contacts?sort_by=lead_source&sort_order=desc", headers=auth_headers_owner)
    assert resp.status_code == 200
    assert [c["first_name"] for c in resp.json()] == ["Alice", "Charlie", "Bob"]

    # 6. created_at: day 1 (Zimmer), day 2 (Adams), day 3 (Brown)
    resp = await client.get("/api/v1/contacts?sort_by=created_at&sort_order=asc", headers=auth_headers_owner)
    assert resp.status_code == 200
    assert [c["last_name"] for c in resp.json()] == ["Zimmer", "Adams", "Brown"]

    resp = await client.get("/api/v1/contacts?sort_by=created_at&sort_order=desc", headers=auth_headers_owner)
    assert resp.status_code == 200
    assert [c["last_name"] for c in resp.json()] == ["Brown", "Adams", "Zimmer"]


@pytest.mark.asyncio
async def test_contacts_sorting_fallbacks(client: AsyncClient, auth_headers_owner: dict, seed_data):
    """Test contacts sort fallbacks when only one parameter is provided."""
    # sort_by=first_name without sort_order -> defaults to asc
    resp = await client.get("/api/v1/contacts?sort_by=first_name", headers=auth_headers_owner)
    assert resp.status_code == 200
    assert [c["first_name"] for c in resp.json()] == ["Alice", "Bob", "Charlie"]

    # sort_by=created_at without sort_order -> defaults to desc
    resp = await client.get("/api/v1/contacts?sort_by=created_at", headers=auth_headers_owner)
    assert resp.status_code == 200
    assert [c["last_name"] for c in resp.json()] == ["Brown", "Adams", "Zimmer"]

    # sort_order=desc without sort_by -> applies desc to default columns (last_name DESC, first_name DESC)
    resp = await client.get("/api/v1/contacts?sort_order=desc", headers=auth_headers_owner)
    assert resp.status_code == 200
    assert [c["last_name"] for c in resp.json()] == ["Zimmer", "Brown", "Adams"]

    # sort_order=asc without sort_by -> applies asc to default columns
    resp = await client.get("/api/v1/contacts?sort_order=asc", headers=auth_headers_owner)
    assert resp.status_code == 200
    assert [c["last_name"] for c in resp.json()] == ["Adams", "Brown", "Zimmer"]


@pytest.mark.asyncio
async def test_contacts_invalid_sort(client: AsyncClient, auth_headers_owner: dict, seed_data):
    """Test contacts sorting validation failures (HTTP 400)."""
    # Invalid sort_by
    resp = await client.get("/api/v1/contacts?sort_by=password", headers=auth_headers_owner)
    assert resp.status_code == 400
    assert "Invalid sort field" in resp.json()["error"]["message"]

    # Invalid sort_order
    resp = await client.get("/api/v1/contacts?sort_order=down", headers=auth_headers_owner)
    assert resp.status_code == 400
    assert "Invalid sort order" in resp.json()["error"]["message"]


# ============================================================================
# COMPANIES FILTERING & SORTING TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_companies_filtering(client: AsyncClient, auth_headers_owner: dict, seed_data):
    """Test companies exact filtering on industry, size, city, country."""
    # Industry (case-insensitive & trimmed)
    resp = await client.get("/api/v1/companies?industry=technology", headers=auth_headers_owner)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["name"] == "Alpha Tech"
    # Ensure Org B's Omega Tech is not returned
    assert all(c["name"] != "Omega Tech" for c in data)

    # Size
    resp = await client.get("/api/v1/companies?size=201-500", headers=auth_headers_owner)
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["name"] == "Beta Logistics"

    # City
    resp = await client.get("/api/v1/companies?city=london", headers=auth_headers_owner)
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["name"] == "Gamma Healthcare"

    # Country
    resp = await client.get("/api/v1/companies?country=USA", headers=auth_headers_owner)
    assert resp.status_code == 200
    assert len(resp.json()) == 2

    # Combined multiple filters
    resp = await client.get("/api/v1/companies?country=USA&industry=Logistics", headers=auth_headers_owner)
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["name"] == "Beta Logistics"

    # Search combined with filter
    resp = await client.get("/api/v1/companies?search=Alpha&industry=Technology", headers=auth_headers_owner)
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["name"] == "Alpha Tech"

    # Non-matching filter returns empty list
    resp = await client.get("/api/v1/companies?city=Tokyo", headers=auth_headers_owner)
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_companies_default_sorting(client: AsyncClient, auth_headers_owner: dict, seed_data):
    """Test companies default sorting order: name ASC."""
    resp = await client.get("/api/v1/companies", headers=auth_headers_owner)
    assert resp.status_code == 200
    assert [c["name"] for c in resp.json()] == ["Alpha Tech", "Beta Logistics", "Gamma Healthcare"]


@pytest.mark.asyncio
async def test_companies_sort_by_all_fields_asc_and_desc(client: AsyncClient, auth_headers_owner: dict, seed_data):
    """Test companies sorting by every allowed field in both ASC and DESC directions with exact sequence assertions."""
    # 1. name: Alpha Tech, Beta Logistics, Gamma Healthcare
    resp = await client.get("/api/v1/companies?sort_by=name&sort_order=asc", headers=auth_headers_owner)
    assert resp.status_code == 200
    assert [c["name"] for c in resp.json()] == ["Alpha Tech", "Beta Logistics", "Gamma Healthcare"]

    resp = await client.get("/api/v1/companies?sort_by=name&sort_order=desc", headers=auth_headers_owner)
    assert resp.status_code == 200
    assert [c["name"] for c in resp.json()] == ["Gamma Healthcare", "Beta Logistics", "Alpha Tech"]

    # 2. domain: alphatech.io, betalogistics.com, gammahealth.org
    resp = await client.get("/api/v1/companies?sort_by=domain&sort_order=asc", headers=auth_headers_owner)
    assert resp.status_code == 200
    assert [c["domain"] for c in resp.json()] == ["alphatech.io", "betalogistics.com", "gammahealth.org"]

    resp = await client.get("/api/v1/companies?sort_by=domain&sort_order=desc", headers=auth_headers_owner)
    assert resp.status_code == 200
    assert [c["domain"] for c in resp.json()] == ["gammahealth.org", "betalogistics.com", "alphatech.io"]

    # 3. industry: Healthcare (Gamma), Logistics (Beta), Technology (Alpha)
    resp = await client.get("/api/v1/companies?sort_by=industry&sort_order=asc", headers=auth_headers_owner)
    assert resp.status_code == 200
    assert [c["industry"] for c in resp.json()] == ["Healthcare", "Logistics", "Technology"]

    resp = await client.get("/api/v1/companies?sort_by=industry&sort_order=desc", headers=auth_headers_owner)
    assert resp.status_code == 200
    assert [c["industry"] for c in resp.json()] == ["Technology", "Logistics", "Healthcare"]

    # 4. size: 1-50 (Gamma), 201-500 (Beta), 51-200 (Alpha)
    resp = await client.get("/api/v1/companies?sort_by=size&sort_order=asc", headers=auth_headers_owner)
    assert resp.status_code == 200
    assert [c["size"] for c in resp.json()] == ["1-50", "201-500", "51-200"]

    resp = await client.get("/api/v1/companies?sort_by=size&sort_order=desc", headers=auth_headers_owner)
    assert resp.status_code == 200
    assert [c["size"] for c in resp.json()] == ["51-200", "201-500", "1-50"]

    # 5. city: Chicago (Beta), London (Gamma), San Francisco (Alpha)
    resp = await client.get("/api/v1/companies?sort_by=city&sort_order=asc", headers=auth_headers_owner)
    assert resp.status_code == 200
    assert [c["city"] for c in resp.json()] == ["Chicago", "London", "San Francisco"]

    resp = await client.get("/api/v1/companies?sort_by=city&sort_order=desc", headers=auth_headers_owner)
    assert resp.status_code == 200
    assert [c["city"] for c in resp.json()] == ["San Francisco", "London", "Chicago"]

    # 6. country: UK (Gamma), USA (Alpha id 001), USA (Beta id 002)
    # Tied USA records broken by Company.id.asc()
    resp = await client.get("/api/v1/companies?sort_by=country&sort_order=asc", headers=auth_headers_owner)
    assert resp.status_code == 200
    assert [c["name"] for c in resp.json()] == ["Gamma Healthcare", "Alpha Tech", "Beta Logistics"]

    resp = await client.get("/api/v1/companies?sort_by=country&sort_order=desc", headers=auth_headers_owner)
    assert resp.status_code == 200
    assert [c["name"] for c in resp.json()] == ["Alpha Tech", "Beta Logistics", "Gamma Healthcare"]

    # 7. created_at: day 1 (Alpha), day 2 (Beta), day 3 (Gamma)
    resp = await client.get("/api/v1/companies?sort_by=created_at&sort_order=asc", headers=auth_headers_owner)
    assert resp.status_code == 200
    assert [c["name"] for c in resp.json()] == ["Alpha Tech", "Beta Logistics", "Gamma Healthcare"]

    resp = await client.get("/api/v1/companies?sort_by=created_at&sort_order=desc", headers=auth_headers_owner)
    assert resp.status_code == 200
    assert [c["name"] for c in resp.json()] == ["Gamma Healthcare", "Beta Logistics", "Alpha Tech"]


@pytest.mark.asyncio
async def test_companies_sorting_fallbacks(client: AsyncClient, auth_headers_owner: dict, seed_data):
    """Test companies sort fallbacks when only one parameter is provided."""
    # sort_by=domain without sort_order -> defaults to asc
    resp = await client.get("/api/v1/companies?sort_by=domain", headers=auth_headers_owner)
    assert resp.status_code == 200
    assert [c["domain"] for c in resp.json()] == ["alphatech.io", "betalogistics.com", "gammahealth.org"]

    # sort_by=created_at without sort_order -> defaults to desc
    resp = await client.get("/api/v1/companies?sort_by=created_at", headers=auth_headers_owner)
    assert resp.status_code == 200
    assert [c["name"] for c in resp.json()] == ["Gamma Healthcare", "Beta Logistics", "Alpha Tech"]

    # sort_order=desc without sort_by -> applies desc to Company.name
    resp = await client.get("/api/v1/companies?sort_order=desc", headers=auth_headers_owner)
    assert resp.status_code == 200
    assert [c["name"] for c in resp.json()] == ["Gamma Healthcare", "Beta Logistics", "Alpha Tech"]

    # sort_order=asc without sort_by -> applies asc to Company.name
    resp = await client.get("/api/v1/companies?sort_order=asc", headers=auth_headers_owner)
    assert resp.status_code == 200
    assert [c["name"] for c in resp.json()] == ["Alpha Tech", "Beta Logistics", "Gamma Healthcare"]


@pytest.mark.asyncio
async def test_companies_invalid_sort(client: AsyncClient, auth_headers_owner: dict, seed_data):
    """Test companies sorting validation failures (HTTP 400)."""
    # Invalid sort_by -> 400
    resp = await client.get("/api/v1/companies?sort_by=revenue", headers=auth_headers_owner)
    assert resp.status_code == 400
    assert "Invalid sort field" in resp.json()["error"]["message"]

    # Invalid sort_order -> 400
    resp = await client.get("/api/v1/companies?sort_order=backwards", headers=auth_headers_owner)
    assert resp.status_code == 400
    assert "Invalid sort order" in resp.json()["error"]["message"]


# ============================================================================
# LEADS FILTERING & SORTING TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_leads_filtering_source_and_priority(client: AsyncClient, auth_headers_owner: dict, seed_data):
    """Test leads filtering by source and priority."""
    # Source (case-insensitive & trimmed)
    resp = await client.get("/api/v1/leads?source=website", headers=auth_headers_owner)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert all(l["source"] == "Website" for l in data)
    # Ensure Org B lead is not returned
    assert all(l["title"] != "Omega Core Expansion" for l in data)

    # Priority (case-insensitive & trimmed)
    resp = await client.get("/api/v1/leads?priority=high", headers=auth_headers_owner)
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["title"] == "Alpha Cloud Migration"

    resp = await client.get("/api/v1/leads?priority=URGENT", headers=auth_headers_owner)
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["title"] == "Gamma Hospital EHR"


@pytest.mark.asyncio
async def test_leads_filtering_value_range(client: AsyncClient, auth_headers_owner: dict, seed_data):
    """Test leads filtering by estimated_value range (min_value, max_value)."""
    # min_value only
    resp = await client.get("/api/v1/leads?min_value=50000", headers=auth_headers_owner)
    assert resp.status_code == 200
    values = sorted([l["estimated_value"] for l in resp.json()])
    assert values == [50000.0, 120000.0]

    # max_value only
    resp = await client.get("/api/v1/leads?max_value=50000", headers=auth_headers_owner)
    assert resp.status_code == 200
    values = sorted([l["estimated_value"] for l in resp.json()])
    assert values == [15000.0, 50000.0]

    # Both min_value and max_value (inclusive range)
    resp = await client.get("/api/v1/leads?min_value=15000&max_value=50000", headers=auth_headers_owner)
    assert resp.status_code == 200
    values = sorted([l["estimated_value"] for l in resp.json()])
    assert values == [15000.0, 50000.0]

    # Strict inside
    resp = await client.get("/api/v1/leads?min_value=20000&max_value=60000", headers=auth_headers_owner)
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["title"] == "Alpha Cloud Migration"


@pytest.mark.asyncio
async def test_leads_value_range_validation(client: AsyncClient, auth_headers_owner: dict, seed_data):
    """Test validation errors for invalid min_value/max_value."""
    # min_value > max_value -> HTTP 400
    resp = await client.get("/api/v1/leads?min_value=100000&max_value=50000", headers=auth_headers_owner)
    assert resp.status_code == 400
    assert "min_value cannot be greater than max_value" in resp.json()["error"]["message"]

    # Negative min_value -> HTTP 422
    resp = await client.get("/api/v1/leads?min_value=-10", headers=auth_headers_owner)
    assert resp.status_code == 422

    # Negative max_value -> HTTP 422
    resp = await client.get("/api/v1/leads?max_value=-1", headers=auth_headers_owner)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_leads_combined_filtering(client: AsyncClient, auth_headers_owner: dict, seed_data):
    """Test combining status, source, priority, value range, and search."""
    resp = await client.get(
        "/api/v1/leads?status=NEW&source=Website&priority=HIGH&min_value=30000&max_value=60000&search=Alpha",
        headers=auth_headers_owner,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["title"] == "Alpha Cloud Migration"

    # Conflicting criteria returns empty list
    resp = await client.get(
        "/api/v1/leads?status=WON&source=Website",
        headers=auth_headers_owner,
    )
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_leads_default_sorting(client: AsyncClient, auth_headers_owner: dict, seed_data):
    """Test leads default sorting order: created_at DESC."""
    resp = await client.get("/api/v1/leads", headers=auth_headers_owner)
    assert resp.status_code == 200
    assert [l["title"] for l in resp.json()] == [
        "Gamma Hospital EHR",
        "Beta Fleet Management",
        "Alpha Cloud Migration",
    ]


@pytest.mark.asyncio
async def test_leads_sort_by_all_fields_asc_and_desc(client: AsyncClient, auth_headers_owner: dict, seed_data):
    """Test leads sorting by every allowed field in both ASC and DESC directions with exact sequence assertions."""
    # 1. title: Alpha Cloud Migration, Beta Fleet Management, Gamma Hospital EHR
    resp = await client.get("/api/v1/leads?sort_by=title&sort_order=asc", headers=auth_headers_owner)
    assert resp.status_code == 200
    assert [l["title"] for l in resp.json()] == [
        "Alpha Cloud Migration",
        "Beta Fleet Management",
        "Gamma Hospital EHR",
    ]

    resp = await client.get("/api/v1/leads?sort_by=title&sort_order=desc", headers=auth_headers_owner)
    assert resp.status_code == 200
    assert [l["title"] for l in resp.json()] == [
        "Gamma Hospital EHR",
        "Beta Fleet Management",
        "Alpha Cloud Migration",
    ]

    # 2. status: CONTACTED (Beta), NEW (Alpha), QUALIFIED (Gamma)
    resp = await client.get("/api/v1/leads?sort_by=status&sort_order=asc", headers=auth_headers_owner)
    assert resp.status_code == 200
    assert [l["status"] for l in resp.json()] == ["CONTACTED", "NEW", "QUALIFIED"]

    resp = await client.get("/api/v1/leads?sort_by=status&sort_order=desc", headers=auth_headers_owner)
    assert resp.status_code == 200
    assert [l["status"] for l in resp.json()] == ["QUALIFIED", "NEW", "CONTACTED"]

    # 3. source: Cold Call (Beta), Website (Alpha id 001), Website (Gamma id 003)
    # Tied Website records broken by Lead.id.asc()
    resp = await client.get("/api/v1/leads?sort_by=source&sort_order=asc", headers=auth_headers_owner)
    assert resp.status_code == 200
    assert [l["title"] for l in resp.json()] == [
        "Beta Fleet Management",
        "Alpha Cloud Migration",
        "Gamma Hospital EHR",
    ]

    resp = await client.get("/api/v1/leads?sort_by=source&sort_order=desc", headers=auth_headers_owner)
    assert resp.status_code == 200
    assert [l["title"] for l in resp.json()] == [
        "Alpha Cloud Migration",
        "Gamma Hospital EHR",
        "Beta Fleet Management",
    ]

    # 4. score: 40 (Beta), 85 (Alpha), 95 (Gamma)
    resp = await client.get("/api/v1/leads?sort_by=score&sort_order=asc", headers=auth_headers_owner)
    assert resp.status_code == 200
    assert [l["score"] for l in resp.json()] == [40, 85, 95]

    resp = await client.get("/api/v1/leads?sort_by=score&sort_order=desc", headers=auth_headers_owner)
    assert resp.status_code == 200
    assert [l["score"] for l in resp.json()] == [95, 85, 40]

    # 5. priority: HIGH (Alpha), LOW (Beta), URGENT (Gamma)
    # Alphabetical order of strings: 'HIGH' < 'LOW' < 'URGENT'
    resp = await client.get("/api/v1/leads?sort_by=priority&sort_order=asc", headers=auth_headers_owner)
    assert resp.status_code == 200
    assert [l["priority"] for l in resp.json()] == ["HIGH", "LOW", "URGENT"]

    resp = await client.get("/api/v1/leads?sort_by=priority&sort_order=desc", headers=auth_headers_owner)
    assert resp.status_code == 200
    assert [l["priority"] for l in resp.json()] == ["URGENT", "LOW", "HIGH"]

    # 6. estimated_value: 15000.0 (Beta), 50000.0 (Alpha), 120000.0 (Gamma)
    resp = await client.get("/api/v1/leads?sort_by=estimated_value&sort_order=asc", headers=auth_headers_owner)
    assert resp.status_code == 200
    assert [l["estimated_value"] for l in resp.json()] == [15000.0, 50000.0, 120000.0]

    resp = await client.get("/api/v1/leads?sort_by=estimated_value&sort_order=desc", headers=auth_headers_owner)
    assert resp.status_code == 200
    assert [l["estimated_value"] for l in resp.json()] == [120000.0, 50000.0, 15000.0]

    # 7. created_at: day 1 (Alpha), day 2 (Beta), day 3 (Gamma)
    resp = await client.get("/api/v1/leads?sort_by=created_at&sort_order=asc", headers=auth_headers_owner)
    assert resp.status_code == 200
    assert [l["title"] for l in resp.json()] == [
        "Alpha Cloud Migration",
        "Beta Fleet Management",
        "Gamma Hospital EHR",
    ]

    resp = await client.get("/api/v1/leads?sort_by=created_at&sort_order=desc", headers=auth_headers_owner)
    assert resp.status_code == 200
    assert [l["title"] for l in resp.json()] == [
        "Gamma Hospital EHR",
        "Beta Fleet Management",
        "Alpha Cloud Migration",
    ]


@pytest.mark.asyncio
async def test_leads_sorting_fallbacks(client: AsyncClient, auth_headers_owner: dict, seed_data):
    """Test leads sort fallbacks when only one parameter is provided."""
    # sort_by=score without sort_order -> defaults to asc
    resp = await client.get("/api/v1/leads?sort_by=score", headers=auth_headers_owner)
    assert resp.status_code == 200
    assert [l["score"] for l in resp.json()] == [40, 85, 95]

    # sort_by=created_at without sort_order -> defaults to desc
    resp = await client.get("/api/v1/leads?sort_by=created_at", headers=auth_headers_owner)
    assert resp.status_code == 200
    assert [l["title"] for l in resp.json()] == [
        "Gamma Hospital EHR",
        "Beta Fleet Management",
        "Alpha Cloud Migration",
    ]

    # sort_order=asc without sort_by -> applies asc to Lead.created_at
    resp = await client.get("/api/v1/leads?sort_order=asc", headers=auth_headers_owner)
    assert resp.status_code == 200
    assert [l["title"] for l in resp.json()] == [
        "Alpha Cloud Migration",
        "Beta Fleet Management",
        "Gamma Hospital EHR",
    ]

    # sort_order=desc without sort_by -> applies desc to Lead.created_at
    resp = await client.get("/api/v1/leads?sort_order=desc", headers=auth_headers_owner)
    assert resp.status_code == 200
    assert [l["title"] for l in resp.json()] == [
        "Gamma Hospital EHR",
        "Beta Fleet Management",
        "Alpha Cloud Migration",
    ]


@pytest.mark.asyncio
async def test_leads_invalid_sort(client: AsyncClient, auth_headers_owner: dict, seed_data):
    """Test leads sorting validation failures (HTTP 400)."""
    # Invalid sort_by -> HTTP 400
    resp = await client.get("/api/v1/leads?sort_by=secret", headers=auth_headers_owner)
    assert resp.status_code == 400
    assert "Invalid sort field" in resp.json()["error"]["message"]

    # Invalid sort_order -> HTTP 400
    resp = await client.get("/api/v1/leads?sort_order=random", headers=auth_headers_owner)
    assert resp.status_code == 400
    assert "Invalid sort order" in resp.json()["error"]["message"]


# ============================================================================
# PAGINATION TESTS WITH SORTING & TIE BREAKERS
# ============================================================================

@pytest.mark.asyncio
async def test_pagination_with_filters_and_sorting(client: AsyncClient, auth_headers_owner: dict, seed_data):
    """Test limit and offset with sorting on unique values."""
    # Leads sorted by score asc with limit=2, offset=0
    resp = await client.get("/api/v1/leads?sort_by=score&sort_order=asc&limit=2&offset=0", headers=auth_headers_owner)
    assert resp.status_code == 200
    assert [l["score"] for l in resp.json()] == [40, 85]

    # offset=2
    resp = await client.get("/api/v1/leads?sort_by=score&sort_order=asc&limit=2&offset=2", headers=auth_headers_owner)
    assert resp.status_code == 200
    assert [l["score"] for l in resp.json()] == [95]


@pytest.mark.asyncio
async def test_pagination_deterministic_on_tied_sort_values(client: AsyncClient, auth_headers_owner: dict, seed_data):
    """Test deterministic pagination when multiple records share the same primary sort value."""
    # Leads sorted by source asc: "Cold Call" (Beta), "Website" (Alpha id 001), "Website" (Gamma id 003)
    # Page 1 (limit=1, offset=0)
    p1 = await client.get("/api/v1/leads?sort_by=source&sort_order=asc&limit=1&offset=0", headers=auth_headers_owner)
    assert p1.status_code == 200
    assert [l["title"] for l in p1.json()] == ["Beta Fleet Management"]

    # Page 2 (limit=1, offset=1) -> First of the tied "Website" records via id.asc()
    p2 = await client.get("/api/v1/leads?sort_by=source&sort_order=asc&limit=1&offset=1", headers=auth_headers_owner)
    assert p2.status_code == 200
    assert [l["title"] for l in p2.json()] == ["Alpha Cloud Migration"]

    # Page 3 (limit=1, offset=2) -> Second of the tied "Website" records via id.asc()
    p3 = await client.get("/api/v1/leads?sort_by=source&sort_order=asc&limit=1&offset=2", headers=auth_headers_owner)
    assert p3.status_code == 200
    assert [l["title"] for l in p3.json()] == ["Gamma Hospital EHR"]


@pytest.mark.asyncio
async def test_contacts_pagination_deterministic_and_non_overlapping(client: AsyncClient, auth_headers_owner: dict, seed_data):
    """Contacts pagination returns deterministic, non-overlapping pages across offset increments."""
    # Sorted by last_name asc: Adams, Brown, Zimmer
    p1 = await client.get("/api/v1/contacts?sort_by=last_name&sort_order=asc&limit=1&offset=0", headers=auth_headers_owner)
    assert p1.status_code == 200
    assert [c["last_name"] for c in p1.json()] == ["Adams"]
    c1_id = p1.json()[0]["id"]

    p2 = await client.get("/api/v1/contacts?sort_by=last_name&sort_order=asc&limit=1&offset=1", headers=auth_headers_owner)
    assert p2.status_code == 200
    assert [c["last_name"] for c in p2.json()] == ["Brown"]
    c2_id = p2.json()[0]["id"]

    p3 = await client.get("/api/v1/contacts?sort_by=last_name&sort_order=asc&limit=1&offset=2", headers=auth_headers_owner)
    assert p3.status_code == 200
    assert [c["last_name"] for c in p3.json()] == ["Zimmer"]
    c3_id = p3.json()[0]["id"]

    # Assert all returned contact IDs are distinct (non-overlapping)
    assert len({c1_id, c2_id, c3_id}) == 3


@pytest.mark.asyncio
async def test_companies_pagination_deterministic_and_non_overlapping(client: AsyncClient, auth_headers_owner: dict, seed_data):
    """Companies pagination returns deterministic, non-overlapping pages across offset increments."""
    # Sorted by name asc: Alpha Tech, Beta Logistics, Gamma Healthcare
    p1 = await client.get("/api/v1/companies?sort_by=name&sort_order=asc&limit=1&offset=0", headers=auth_headers_owner)
    assert p1.status_code == 200
    assert [c["name"] for c in p1.json()] == ["Alpha Tech"]
    comp1_id = p1.json()[0]["id"]

    p2 = await client.get("/api/v1/companies?sort_by=name&sort_order=asc&limit=1&offset=1", headers=auth_headers_owner)
    assert p2.status_code == 200
    assert [c["name"] for c in p2.json()] == ["Beta Logistics"]
    comp2_id = p2.json()[0]["id"]

    p3 = await client.get("/api/v1/companies?sort_by=name&sort_order=asc&limit=1&offset=2", headers=auth_headers_owner)
    assert p3.status_code == 200
    assert [c["name"] for c in p3.json()] == ["Gamma Healthcare"]
    comp3_id = p3.json()[0]["id"]

    # Assert all returned company IDs are distinct (non-overlapping)
    assert len({comp1_id, comp2_id, comp3_id}) == 3


@pytest.mark.asyncio
async def test_pagination_offset_beyond_result_count_returns_empty_list(client: AsyncClient, auth_headers_owner: dict, seed_data):
    """An offset larger than the total matching count returns HTTP 200 with an empty list."""
    res_contacts = await client.get("/api/v1/contacts?limit=10&offset=100", headers=auth_headers_owner)
    assert res_contacts.status_code == 200
    assert res_contacts.json() == []

    res_companies = await client.get("/api/v1/companies?limit=10&offset=100", headers=auth_headers_owner)
    assert res_companies.status_code == 200
    assert res_companies.json() == []

    res_leads = await client.get("/api/v1/leads?limit=10&offset=100", headers=auth_headers_owner)
    assert res_leads.status_code == 200
    assert res_leads.json() == []
