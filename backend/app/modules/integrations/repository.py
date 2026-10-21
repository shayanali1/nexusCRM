"""Repository layer for tenant-scoped integration configurations."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.integrations.crypto import decrypt_credentials, encrypt_credentials
from app.modules.integrations.models import Integration


class IntegrationRepository:
    """Provides tenant-isolated CRUD operations for third-party integrations."""

    def __init__(self, db: AsyncSession, organization_id: str):
        self.db = db
        self.org_id = organization_id

    async def list_all(self) -> List[Integration]:
        """List all integration configurations configured for the current organization."""
        stmt = (
            select(Integration)
            .where(Integration.organization_id == self.org_id)
            .order_by(Integration.created_at.asc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_by_provider(self, provider: str) -> Optional[Integration]:
        """Retrieve a single integration by provider name for the current organization."""
        stmt = select(Integration).where(
            Integration.organization_id == self.org_id,
            Integration.provider == provider,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert(
        self,
        provider: str,
        is_active: Optional[bool] = None,
        config: Optional[Dict[str, Any]] = None,
        credentials: Optional[Dict[str, Any]] = None,
        credentials_provided: bool = False,
    ) -> Integration:
        """Create or update an integration configuration for the current organization.

        If credentials_provided is False, existing credentials are strictly preserved.
        If credentials_provided is True and credentials is empty ({}) or None, credentials are cleared.
        If credentials_provided is True and non-empty, credentials are encrypted and stored.
        """
        existing = await self.get_by_provider(provider)

        if existing:
            if is_active is not None:
                existing.is_active = is_active
            if config is not None:
                existing.config = config
            if credentials_provided:
                if not credentials:
                    existing.credentials = {}
                else:
                    existing.credentials = encrypt_credentials(credentials)

            existing.updated_at = datetime.now(timezone.utc)
            await self.db.flush()
            await self.db.refresh(existing)
            return existing

        # Create new record
        if credentials_provided and credentials:
            encrypted_creds = encrypt_credentials(credentials)
        else:
            encrypted_creds = {}

        new_integration = Integration(
            organization_id=self.org_id,
            provider=provider,
            is_active=is_active if is_active is not None else False,
            config=config if config is not None else {},
            credentials=encrypted_creds,
        )

        try:
            self.db.add(new_integration)
            await self.db.flush()
            await self.db.refresh(new_integration)
            return new_integration
        except IntegrityError:
            # Handle concurrent creation conflict on unique index ix_integrations_org_provider
            await self.db.rollback()
            existing = await self.get_by_provider(provider)
            if existing:
                if is_active is not None:
                    existing.is_active = is_active
                if config is not None:
                    existing.config = config
                if credentials_provided:
                    if not credentials:
                        existing.credentials = {}
                    else:
                        existing.credentials = encrypt_credentials(credentials)
                existing.updated_at = datetime.now(timezone.utc)
                await self.db.flush()
                await self.db.refresh(existing)
                return existing
            raise

    async def delete(self, integration: Integration) -> None:
        """Permanently remove an integration configuration and purge stored credentials."""
        await self.db.delete(integration)
        await self.db.flush()

    def get_decrypted_credentials(self, integration: Integration) -> Dict[str, Any]:
        """Internal helper to decrypt credentials for trusted background task execution.

        Never expose this through public API routes.
        """
        return decrypt_credentials(integration.credentials)
