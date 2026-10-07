from typing import List
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.exceptions import ConflictException, NotFoundException
from app.core.permissions import Permission
from app.core.security import hash_password
from app.modules.auth.dependencies import get_current_user, require_permission
from app.modules.users.models import User
from app.modules.users.repository import UserRepository
from app.modules.users.schemas import UserCreate, UserResponse, UserUpdate

router = APIRouter(prefix="/users", tags=["Users & Team"])


@router.get("", response_model=List[UserResponse])
async def list_team_members(
    current_user: User = Depends(require_permission(Permission.TEAM_READ)),
    db: AsyncSession = Depends(get_db),
):
    """List all team members within the active organization."""
    repo = UserRepository(db, current_user.organization_id)
    users = await repo.list_all()
    return [UserResponse.model_validate(u) for u in users]


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def invite_or_create_user(
    req: UserCreate,
    current_user: User = Depends(require_permission(Permission.TEAM_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    """Add a new user / team member to the organization."""
    repo = UserRepository(db, current_user.organization_id)
    existing = await repo.get_by_email(req.email)
    if existing:
        raise ConflictException("User with this email already exists in this organization.")

    user = await repo.create(req, hash_password(req.password))
    return UserResponse.model_validate(user)


@router.get("/{user_id}", response_model=UserResponse)
async def get_user_by_id(
    user_id: str,
    current_user: User = Depends(require_permission(Permission.TEAM_READ)),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve specific user details scoped to organization."""
    repo = UserRepository(db, current_user.organization_id)
    user = await repo.get_by_id(user_id)
    if not user:
        raise NotFoundException("User not found in this organization.")
    return UserResponse.model_validate(user)


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str,
    req: UserUpdate,
    current_user: User = Depends(require_permission(Permission.TEAM_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    """Update team member role or profile status."""
    repo = UserRepository(db, current_user.organization_id)
    user = await repo.get_by_id(user_id)
    if not user:
        raise NotFoundException("User not found.")
    updated = await repo.update(user, req)
    return UserResponse.model_validate(updated)
