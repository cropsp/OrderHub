"""
OrderHub CRM — User Schemas
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr

from models.user import UserRole


class UserBase(BaseModel):
    email: EmailStr
    full_name: str
    role: UserRole


class UserCreate(UserBase):
    """Owner creates a new user — password is auto-generated."""
    pass


class UserUpdate(BaseModel):
    full_name: str | None = None
    role: UserRole | None = None
    is_active: bool | None = None


class UserPreferencesUpdate(BaseModel):
    preferences: dict


class UserResponse(UserBase):
    id: uuid.UUID
    is_active: bool
    preferences: dict
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UserWithPasswordResponse(UserResponse):
    """Returned only on user creation — shows the temporary password once."""
    temporary_password: str
