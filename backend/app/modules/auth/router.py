from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.modules.auth.dependencies import get_current_organization, get_current_user
from app.modules.auth.schemas import LoginRequest, RefreshTokenRequest, RegisterRequest, TokenResponse
from app.modules.auth.service import AuthService
from app.modules.organizations.models import Organization
from app.modules.organizations.schemas import OrganizationResponse
from app.modules.users.models import User
from app.modules.users.schemas import UserResponse

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    req: RegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    """Register a new organization workspace and initial Owner account."""
    service = AuthService(db)
    return await service.register(req)


@router.post("/login", response_model=TokenResponse)
async def login(
    req: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """Log into an organization with email and password."""
    service = AuthService(db)
    return await service.login(req)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_tokens(
    req: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
):
    """Exchange a valid refresh token for a fresh access & refresh token pair."""
    service = AuthService(db)
    return await service.refresh_tokens(req)


@router.get("/me")
async def get_current_user_profile(
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
):
    """Retrieve the profile and tenant context of the currently authenticated user."""
    return {
        "user": UserResponse.model_validate(current_user),
        "organization": OrganizationResponse.model_validate(current_org),
    }
