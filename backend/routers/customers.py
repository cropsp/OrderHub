"""
OrderHub CRM — Customers Router
"""

import uuid
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select, func, or_
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.user import User
from models.customer import Customer
from models.order import Order
from schemas.customer import CustomerResponse
from schemas.common import PaginatedResponse
from routers.dependencies import get_current_user
from services.customer_service import get_customer_with_order_count

router = APIRouter(prefix="/api/customers", tags=["customers"])


@router.get("", response_model=PaginatedResponse[CustomerResponse])
async def list_customers(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    search: str | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List customers with order counts and search."""
    skip = (page - 1) * limit
    
    # Base queries
    query = select(Customer)
    count_query = select(func.count()).select_from(Customer)
    
    if search:
        term = f"%{search}%"
        conditions = [Customer.email.ilike(term), Customer.full_name.ilike(term)]
        query = query.where(or_(*conditions))
        count_query = count_query.where(or_(*conditions))
        
    total = await db.scalar(count_query) or 0
    pages = (total + limit - 1) // limit
    
    query = query.order_by(Customer.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    customers = list(result.scalars().all())
    
    # We need to compute order_count for each (in a real app this might be a subquery)
    # For now, we do individual queries since list size is small
    responses = []
    for c in customers:
        c_with_count = await get_customer_with_order_count(db, c.id)
        responses.append(CustomerResponse.model_validate(c_with_count))
        
    return PaginatedResponse[CustomerResponse](
        items=responses,
        total=total,
        page=page,
        limit=limit,
        pages=pages
    )


@router.get("/{customer_id}", response_model=CustomerResponse)
async def get_customer(
    customer_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get customer details and order count."""
    customer = await get_customer_with_order_count(db, customer_id)
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
        
    return customer
