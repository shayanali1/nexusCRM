import asyncio
import os
import sys
from typing import AsyncGenerator, Dict
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Add backend directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Force test configuration
os.environ["APP_ENV"] = "test"
os.environ["AI_PROVIDER"] = "mock"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

from app.core.database import Base, get_db
from app.core.security import create_access_token, hash_password
import app.models
from app.main import app
from app.modules.organizations.models import Organization
from app.modules.pipelines.models import Pipeline, PipelineStage
from app.modules.users.models import User

# Test database engine
test_engine = create_async_engine(
    "sqlite+aiosqlite:///:memory:",
    connect_args={"check_same_thread": False},
)
TestAsyncSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


@pytest_asyncio.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Create a fresh isolated in-memory database per test."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with TestAsyncSessionLocal() as session:
        yield session

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(scope="function")
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Provide AsyncClient overriding the database dependency."""

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture(scope="function")
async def test_org(db_session: AsyncSession) -> Organization:
    """Create test organization A."""
    org = Organization(
        name="Org Alpha",
        slug="org-alpha",
        plan="starter",
        is_active=True,
    )
    db_session.add(org)
    await db_session.flush()

    # Create default pipeline
    pipe = Pipeline(organization_id=org.id, name="Sales Pipeline", is_default=True)
    db_session.add(pipe)
    await db_session.flush()

    stage = PipelineStage(
        organization_id=org.id,
        pipeline_id=pipe.id,
        name="New",
        order=1,
        win_probability=10,
    )
    db_session.add(stage)
    await db_session.commit()
    await db_session.refresh(org)
    return org


@pytest_asyncio.fixture(scope="function")
async def test_user_owner(db_session: AsyncSession, test_org: Organization) -> User:
    """Create test Owner user in Organization A."""
    user = User(
        organization_id=test_org.id,
        email="owner@alpha.com",
        hashed_password=hash_password("password123"),
        first_name="Alice",
        last_name="Owner",
        role="OWNER",
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture(scope="function")
async def test_user_member(db_session: AsyncSession, test_org: Organization) -> User:
    """Create test Member user in Organization A."""
    user = User(
        organization_id=test_org.id,
        email="member@alpha.com",
        hashed_password=hash_password("password123"),
        first_name="Bob",
        last_name="Member",
        role="MEMBER",
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def auth_headers_owner(test_user_owner: User, test_org: Organization) -> Dict[str, str]:
    """Return authorization headers for Organization A Owner."""
    token = create_access_token(test_user_owner.id, test_org.id, test_user_owner.role)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_headers_member(test_user_member: User, test_org: Organization) -> Dict[str, str]:
    """Return authorization headers for Organization A Member."""
    token = create_access_token(test_user_member.id, test_org.id, test_user_member.role)
    return {"Authorization": f"Bearer {token}"}
