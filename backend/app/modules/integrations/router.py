"""FastAPI REST router for secure third-party integration management."""

from typing import List
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import BadRequestException, NotFoundException
from app.core.permissions import Permission
from app.modules.auth.dependencies import require_permission
from app.modules.integrations.crypto import has_configured_credentials
from app.modules.integrations.models import Integration
from app.modules.integrations.repository import IntegrationRepository
from app.modules.integrations.schemas import (
    SUPPORTED_PROVIDERS,
    IntegrationResponse,
    IntegrationUpsertRequest,
)
from app.modules.users.models import User

router = APIRouter(prefix="/integrations", tags=["Integrations"])


def _normalize_and_validate_provider(provider: str) -> str:
    """Normalize and validate provider identifier against supported providers."""
    clean_provider = provider.strip().lower()
    if clean_provider not in SUPPORTED_PROVIDERS:
        raise BadRequestException(
            f"Unsupported integration provider '{provider}'. Supported providers: {', '.join(sorted(SUPPORTED_PROVIDERS))}."
        )
    return clean_provider


def _to_integration_response(integration: Integration) -> IntegrationResponse:
    """Transform internal Integration model to safe public response without secrets."""
    return IntegrationResponse(
        id=integration.id,
        provider=integration.provider,
        is_active=integration.is_active,
        config=integration.config or {},
        has_credentials=has_configured_credentials(integration.credentials),
        created_at=integration.created_at,
        updated_at=integration.updated_at,
    )


@router.get("", response_model=List[IntegrationResponse])
async def list_integrations(
    current_user: User = Depends(require_permission(Permission.INTEGRATIONS_READ)),
    db: AsyncSession = Depends(get_db),
):
    """List all configured integrations for the authenticated organization."""
    repo = IntegrationRepository(db, current_user.organization_id)
    items = await repo.list_all()
    return [_to_integration_response(item) for item in items]


@router.get("/{provider}", response_model=IntegrationResponse)
async def get_integration(
    provider: str,
    current_user: User = Depends(require_permission(Permission.INTEGRATIONS_READ)),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve integration configuration for a specific provider by name."""
    norm_provider = _normalize_and_validate_provider(provider)
    repo = IntegrationRepository(db, current_user.organization_id)
    item = await repo.get_by_provider(norm_provider)
    if not item:
        raise NotFoundException(f"Integration '{norm_provider}' not found for this organization.")
    return _to_integration_response(item)


@router.post("/{provider}", response_model=IntegrationResponse)
async def upsert_integration(
    provider: str,
    req: IntegrationUpsertRequest,
    current_user: User = Depends(require_permission(Permission.INTEGRATIONS_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    """Create or update integration configuration and credentials for a provider.

    Omitting credentials preserves previously encrypted credentials.
    Explicitly supplying an empty dictionary {} clears credentials.
    Non-secret configuration cannot contain recognized secret keys.
    """
    norm_provider = _normalize_and_validate_provider(provider)
    if req.provider and req.provider.strip().lower() != norm_provider:
        raise BadRequestException("Provider in request body does not match path parameter.")

    credentials_provided = "credentials" in req.model_fields_set

    repo = IntegrationRepository(db, current_user.organization_id)
    item = await repo.upsert(
        provider=norm_provider,
        is_active=req.is_active,
        config=req.config,
        credentials=req.credentials,
        credentials_provided=credentials_provided,
    )
    await db.commit()
    return _to_integration_response(item)


@router.delete("/{provider}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_integration(
    provider: str,
    current_user: User = Depends(require_permission(Permission.INTEGRATIONS_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    """Permanently remove an integration configuration and purge stored credentials."""
    norm_provider = _normalize_and_validate_provider(provider)
    repo = IntegrationRepository(db, current_user.organization_id)
    item = await repo.get_by_provider(norm_provider)
    if not item:
        raise NotFoundException(f"Integration '{norm_provider}' not found for this organization.")

    await repo.delete(item)
    await db.commit()
