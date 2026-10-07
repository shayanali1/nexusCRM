from typing import Callable
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.exceptions import ForbiddenException, NotFoundException, TenantIsolationException, UnauthorizedException
from app.core.permissions import Permission, has_permission
from app.core.security import decode_token
from app.modules.organizations.models import Organization
from app.modules.users.models import User

bearer_scheme = HTTPBearer(auto_error=False)


async def get_token_payload(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> dict:
    """Extract and validate JWT payload from Bearer token."""
    if not credentials or not credentials.credentials:
        raise UnauthorizedException("Authentication token is missing.")
    return decode_token(credentials.credentials)


async def get_current_user(
    payload: dict = Depends(get_token_payload),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Load authenticated user and ensure they exist and are active in their tenant."""
    user_id = payload.get("sub")
    org_id = payload.get("org_id")

    if not user_id or not org_id:
        raise UnauthorizedException("Invalid token payload structure.")

    stmt = select(User).where(User.id == user_id, User.organization_id == org_id, User.is_active.is_(True))
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        raise UnauthorizedException("User account not found, deactivated, or mismatch with organization.")

    return user


async def get_current_organization(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Organization:
    """Load and return the validated tenant organization boundary."""
    stmt = select(Organization).where(
        Organization.id == current_user.organization_id,
        Organization.is_active.is_(True),
    )
    result = await db.execute(stmt)
    org = result.scalar_one_or_none()

    if not org:
        raise NotFoundException("Active workspace organization not found.")

    return org


def require_permission(permission: Permission) -> Callable:
    """Dependency factory checking if current user has the required RBAC permission."""

    async def permission_checker(current_user: User = Depends(get_current_user)) -> User:
        if not has_permission(current_user.role, permission):
            raise ForbiddenException(
                f"You lack the required permission '{permission.value}' to perform this action."
            )
        return current_user

    return permission_checker
