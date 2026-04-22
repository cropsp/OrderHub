"""
OrderHub CRM — Customer Schemas
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class CustomerCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(..., max_length=255)
    country: str | None = Field(None, max_length=2)


class CustomerResponse(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    country: str | None
    phone: str | None = None
    shipping_city: str | None = None
    shipping_city_ref: str | None = None
    shipping_warehouse_ref: str | None = None
    created_at: datetime
    updated_at: datetime
    
    order_count: int = 0  # computed field

    model_config = ConfigDict(from_attributes=True)
