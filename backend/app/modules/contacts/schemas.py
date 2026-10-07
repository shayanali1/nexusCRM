from datetime import datetime
from typing import Any, Dict, Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ContactBase(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    title: Optional[str] = None
    lead_source: Optional[str] = "Website"
    address: Optional[str] = None
    company_id: Optional[str] = None
    custom_fields: Dict[str, Any] = Field(default_factory=dict)


class ContactCreate(ContactBase):
    pass


class ContactUpdate(BaseModel):
    first_name: Optional[str] = Field(None, min_length=1, max_length=100)
    last_name: Optional[str] = Field(None, min_length=1, max_length=100)
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    title: Optional[str] = None
    lead_source: Optional[str] = None
    address: Optional[str] = None
    company_id: Optional[str] = None
    custom_fields: Optional[Dict[str, Any]] = None


class ContactResponse(ContactBase):
    id: str
    organization_id: str
    company_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
