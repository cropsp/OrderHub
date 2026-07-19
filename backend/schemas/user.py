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
    """Owner creates a new user — password is auto-generated.

    `shop_ids` sets initial shop access (USER-ACCESS-1). When omitted, a MANAGER
    defaults to all active shops (preserves today's invariant) and a DESIGNER to
    none. Ignored for OWNER (unrestricted).
    """
    shop_ids: list[uuid.UUID] | None = None


class UserUpdate(BaseModel):
    full_name: str | None = None
    role: UserRole | None = None
    is_active: bool | None = None


class ShopAccessResponse(BaseModel):
    """A user's granted shop ids (USER-ACCESS-1)."""
    shop_ids: list[uuid.UUID]


class ShopAccessUpdate(BaseModel):
    """Replace a user's shop grants. `unassign_orders` confirms unassigning the
    user's orders in any shop being revoked (BLOCKING 3)."""
    shop_ids: list[uuid.UUID]
    unassign_orders: bool = False


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
