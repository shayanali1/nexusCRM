import pytest
from app.modules.ai.openai_provider import OpenAIProvider
from app.modules.ai.schemas import LeadSummaryRequest


@pytest.mark.asyncio
async def test_openai_missing_key_graceful_fallback():
    """Test that OpenAIProvider without valid API key gracefully falls back to Mock provider rather than crashing."""
    provider = OpenAIProvider(api_key="")
    assert provider.is_available is False

    req = LeadSummaryRequest(
        contact_name="Ahmed Khan",
        company_name="Apex Logistics",
        stage="Proposal",
        estimated_value=24500.0,
    )
    result = await provider.generate_summary(req)
    assert result is not None
    assert "Ahmed Khan" in result.summary
    assert result.confidence > 0.8
