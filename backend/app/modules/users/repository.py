from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.users.models import User
from app.modules.users.schemas import UserCreate, UserUpdate


class UserRepository:
    def __init__(self, db: AsyncSession, organization_id: str):
        self.db = db
        self.org_id = organization_id

    async def list_all(self) -> List[User]:
        stmt = select(User).where(User.organization_id == self.org_id).order_by(User.first_name)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id(self, user_id: str) -> Optional[User]:
        stmt = select(User).where(User.id == user_id, User.organization_id == self.org_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> Optional[User]:
        stmt = select(User).where(User.email == email.lower(), User.organization_id == self.org_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, user_data: UserCreate, hashed_password: str) -> User:
        user = User(
            organization_id=self.org_id,
            email=user_data.email.lower(),
            hashed_password=hashed_password,
            first_name=user_data.first_name,
            last_name=user_data.last_name,
            role=user_data.role.value,
            phone=user_data.phone,
            avatar_url=user_data.avatar_url,
            is_active=True,
            is_verified=True,
        )
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def update(self, user: User, update_data: UserUpdate) -> User:
        for field, value in update_data.model_dump(exclude_unset=True).items():
            if field == "role" and value is not None:
                user.role = value.value if hasattr(value, "value") else str(value)
            else:
                setattr(user, field, value)
        await self.db.commit()
        await self.db.refresh(user)
        return user
