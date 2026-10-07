from typing import Optional
from pydantic import BaseModel, EmailStr, Field
from app.modules.organizations.schemas import OrganizationResponse
from app.modules.users.schemas import UserResponse


class RegisterRequest(BaseModel):
    organization_name: str = Field(..., min_length=2, max_length=255)
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    organization_id: Optional[str] = None


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse
    organization: OrganizationResponse
