import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_and_convert_lead(client: AsyncClient, auth_headers_owner, mock_celery_dispatch):
    """Test full customer lifecycle: lead creation -> qualification -> deal conversion."""
    # 1. Create Lead with inline contact & company
    create_payload = {
        "title": "FinTech Cloud Migration",
        "contact_name": "Sarah Connor",
        "contact_email": "sarah@skynet.ai",
        "contact_phone": "+1 555-0199",
        "company_name": "Cyberdyne Systems",
        "status": "NEW",
        "source": "Website",
        "estimated_value": 35000.0,
    }
    res = await client.post("/api/v1/leads", json=create_payload, headers=auth_headers_owner)
    assert res.status_code == 201
    lead = res.json()
    assert lead["title"] == "FinTech Cloud Migration"
    assert lead["contact_name"] == "Sarah Connor"
    assert lead["company_name"] == "Cyberdyne Systems"
    lead_id = lead["id"]

    # 2. Convert Lead to Deal
    convert_payload = {
        "deal_title": "Cyberdyne Cloud Scope Deal",
        "deal_value": 35000.0,
    }
    res_conv = await client.post(f"/api/v1/leads/{lead_id}/convert", json=convert_payload, headers=auth_headers_owner)
    assert res_conv.status_code == 200
    conv_data = res_conv.json()
    assert conv_data["success"] is True
    assert "deal_id" in conv_data

    # 3. Verify Deal exists in pipeline
    deal_id = conv_data["deal_id"]
    res_deal = await client.get(f"/api/v1/deals/{deal_id}", headers=auth_headers_owner)
    assert res_deal.status_code == 200
    assert res_deal.json()["title"] == "Cyberdyne Cloud Scope Deal"
    assert res_deal.json()["value"] == 35000.0
