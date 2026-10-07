import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_ai_status_endpoint(client: AsyncClient, auth_headers_owner):
    """Test AI layer operational status check."""
    res = await client.get("/api/v1/ai/status", headers=auth_headers_owner)
    assert res.status_code == 200
    data = res.json()
    assert data["provider"] == "mock"
    assert data["is_mock"] is True
    assert data["is_available"] is True


@pytest.mark.asyncio
async def test_mock_ai_summary_generation(client: AsyncClient, auth_headers_owner):
    """Test AI summary returns structured customer brief with zero external costs."""
    payload = {
        "contact_name": "Ahmed Khan",
        "company_name": "Apex Logistics",
        "stage": "Proposal",
        "estimated_value": 24500.0,
        "activities": [{"type": "CALL", "title": "Discovery call completed"}],
        "notes": "Interested in Premium Package. Awaiting quote.",
    }
    res = await client.post("/api/v1/ai/summary", json=payload, headers=auth_headers_owner)
    assert res.status_code == 200
    data = res.json()
    assert "summary" in data
    assert "Ahmed Khan" in data["summary"]
    assert "key_points" in data
    assert len(data["key_points"]) > 0
    assert data["confidence"] > 0.8


@pytest.mark.asyncio
async def test_mock_ai_explainable_lead_prioritization(client: AsyncClient, auth_headers_owner):
    """Test AI returns explainable business reasons for lead score."""
    payload = {
        "lead_title": "Enterprise Rollout",
        "contact_name": "Ahmed Khan",
        "stage": "PROPOSAL",
        "source": "Website",
        "estimated_value": 24500.0,
        "days_since_last_contact": 4,
        "overdue_tasks_count": 1,
    }
    res = await client.post("/api/v1/ai/prioritize", json=payload, headers=auth_headers_owner)
    assert res.status_code == 200
    data = res.json()
    assert data["priority_level"] in ["HIGH", "URGENT"]
    assert len(data["reasons"]) > 0
    assert any("overdue" in r.lower() or "value" in r.lower() for r in data["reasons"])


@pytest.mark.asyncio
async def test_mock_ai_recommended_next_action(client: AsyncClient, auth_headers_owner):
    """Test AI recommends next best action."""
    payload = {
        "contact_name": "Ahmed Khan",
        "stage": "PROPOSAL",
        "last_interaction": "Proposal delivered 3 days ago",
    }
    res = await client.post("/api/v1/ai/next-action", json=payload, headers=auth_headers_owner)
    assert res.status_code == 200
    data = res.json()
    assert "recommended_action" in data
    assert "suggested_task_title" in data
    assert "proposal" in data["recommended_action"].lower()
