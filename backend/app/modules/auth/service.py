from datetime import datetime, timezone
import re
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.exceptions import BadRequestException, ConflictException, UnauthorizedException
from app.core.permissions import RoleEnum
from app.core.security import create_access_token, create_refresh_token, decode_token, hash_password, verify_password
from app.modules.auth.schemas import LoginRequest, RefreshTokenRequest, RegisterRequest, TokenResponse
from app.modules.organizations.models import Organization
from app.modules.organizations.schemas import OrganizationResponse
from app.modules.users.models import User
from app.modules.users.schemas import UserResponse


def generate_slug(name: str) -> str:
    """Generate a clean URL slug from organization name."""
    slug = re.sub(r"[^\w\s-]", "", name.lower()).strip()
    slug = re.sub(r"[-\s]+", "-", slug)
    return slug or "workspace"


class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def register(self, req: RegisterRequest) -> TokenResponse:
        """Register a new organization and root owner user."""
        # 1. Generate unique organization slug
        base_slug = generate_slug(req.organization_name)
        slug = base_slug
        counter = 1
        while True:
            existing_org = (await self.db.execute(select(Organization).where(Organization.slug == slug))).scalar_one_or_none()
            if not existing_org:
                break
            slug = f"{base_slug}-{counter}"
            counter += 1

        org = Organization(
            name=req.organization_name,
            slug=slug,
            plan="starter",
            is_active=True,
            settings={
                "currency": "USD",
                "timezone": "UTC",
                "lead_scoring_enabled": True,
                "default_pipeline_name": "Standard Sales Pipeline",
            },
        )
        self.db.add(org)
        await self.db.flush()

        # 2. Check if email already used in this new org (shouldn't happen on fresh org, but safe check)
        existing_user = (
            await self.db.execute(
                select(User).where(User.organization_id == org.id, User.email == req.email.lower())
            )
        ).scalar_one_or_none()
        if existing_user:
            raise ConflictException("A user with this email already exists in this organization.")

        # 3. Create root Owner user
        user = User(
            organization_id=org.id,
            email=req.email.lower(),
            hashed_password=hash_password(req.password),
            first_name=req.first_name,
            last_name=req.last_name,
            role=RoleEnum.OWNER.value,
            is_active=True,
            is_verified=True,
            last_login_at=datetime.now(timezone.utc),
        )
        self.db.add(user)

        # 4. Create default sales pipeline and stages for the organization
        from app.modules.pipelines.models import Pipeline, PipelineStage
        pipeline = Pipeline(
            organization_id=org.id,
            name="Sales Pipeline",
            is_default=True,
        )
        self.db.add(pipeline)
        await self.db.flush()

        default_stages = [
            ("New", 1, 10),
            ("Contacted", 2, 20),
            ("Qualified", 3, 40),
            ("Interested", 4, 60),
            ("Proposal", 5, 75),
            ("Negotiation", 6, 90),
            ("Won", 7, 100),
            ("Lost", 8, 0),
        ]
        for name, order, prob in default_stages:
            stage = PipelineStage(
                organization_id=org.id,
                pipeline_id=pipeline.id,
                name=name,
                order=order,
                win_probability=prob,
                is_won=(name == "Won"),
                is_lost=(name == "Lost"),
            )
            self.db.add(stage)

        await self.db.commit()
        await self.db.refresh(user)
        await self.db.refresh(org)

        access_token = create_access_token(user.id, org.id, user.role)
        refresh_token = create_refresh_token(user.id, org.id)

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            user=UserResponse.model_validate(user),
            organization=OrganizationResponse.model_validate(org),
        )

    async def login(self, req: LoginRequest) -> TokenResponse:
        """Authenticate user across their organization."""
        # Find user by email (if org_id provided, filter by org; else find matching user)
        stmt = select(User).where(User.email == req.email.lower(), User.is_active.is_(True))
        if req.organization_id:
            stmt = stmt.where(User.organization_id == req.organization_id)

        result = await self.db.execute(stmt)
        users = result.scalars().all()

        if not users:
            raise UnauthorizedException("Invalid email or password.")

        # If multiple organizations have the same email and no org_id specified, pick the first valid matching password
        matched_user: Optional[User] = None
        for u in users:
            if verify_password(req.password, u.hashed_password):
                matched_user = u
                break

        if not matched_user:
            raise UnauthorizedException("Invalid email or password.")

        org = (
            await self.db.execute(
                select(Organization).where(Organization.id == matched_user.organization_id)
            )
        ).scalar_one_or_none()

        if not org or not org.is_active:
            raise UnauthorizedException("Organization account is deactivated or invalid.")

        matched_user.last_login_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(matched_user)

        access_token = create_access_token(matched_user.id, org.id, matched_user.role)
        refresh_token = create_refresh_token(matched_user.id, org.id)

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            user=UserResponse.model_validate(matched_user),
            organization=OrganizationResponse.model_validate(org),
        )

    async def refresh_tokens(self, req: RefreshTokenRequest) -> TokenResponse:
        """Issue new tokens using a valid refresh token."""
        payload = decode_token(req.refresh_token)
        if payload.get("type") != "refresh":
            raise UnauthorizedException("Invalid refresh token type.")

        user_id = payload.get("sub")
        org_id = payload.get("org_id")

        user = (
            await self.db.execute(
                select(User).where(User.id == user_id, User.organization_id == org_id, User.is_active.is_(True))
            )
        ).scalar_one_or_none()

        org = (
            await self.db.execute(
                select(Organization).where(Organization.id == org_id, Organization.is_active.is_(True))
            )
        ).scalar_one_or_none()

        if not user or not org:
            raise UnauthorizedException("Session is no longer valid.")

        access_token = create_access_token(user.id, org.id, user.role)
        new_refresh = create_refresh_token(user.id, org.id)

        return TokenResponse(
            access_token=access_token,
            refresh_token=new_refresh,
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            user=UserResponse.model_validate(user),
            organization=OrganizationResponse.model_validate(org),
        )
