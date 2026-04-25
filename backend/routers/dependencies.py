"""
OrderHub CRM — Route Dependencies

Shared FastAPI dependencies for authentication and authorization.
"""

import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.user import User, UserRole
from services.auth_service import decode_token, get_user_by_id

security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Extract and validate the current user from the access token."""
    payload = decode_token(credentials.credentials)
    if not payload or payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
        )

    user = await get_user_by_id(db, uuid.UUID(payload["sub"]))
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )
    return user


def require_role(*roles: UserRole):
    """
    Dependency factory that checks if the current user has one of the required roles.

    Usage:
        @router.get("/admin-only")
        async def admin_route(user: User = Depends(require_role(UserRole.OWNER))):
            ...
    """

    async def role_checker(
        current_user: User = Depends(get_current_user),
    ) -> User:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of roles: {', '.join(r.value for r in roles)}",
            )
        return current_user

    return role_checker


async def get_shop_for_user(
    shop_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Fetch a shop and verify the current user has access to it.

    Owner/manager: access to any shop. Designer: only shops where they have at
    least one assigned order. A designer with zero assignments gets 403 on every
    shop-scoped endpoint — see CLAUDE.md Gotchas (SEC-05).
    """
    from models.shop import Shop
    from models.order import Order
    from sqlalchemy import select

    result = await db.execute(select(Shop).filter(Shop.id == shop_id))
    shop = result.scalar_one_or_none()

    if not shop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shop not found",
        )

    if current_user.role == UserRole.DESIGNER:
        assignment = await db.execute(
            select(Order.id)
            .where(Order.shop_id == shop_id)
            .where(Order.assigned_designer_id == current_user.id)
            .limit(1)
        )
        if assignment.scalar_one_or_none() is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not assigned to this shop",
            )

    return shop


def require_platform(platform_name: str):
    """Dependency factory to enforce a specific shop platform (e.g. MANUAL)."""
    async def platform_checker(shop=Depends(get_shop_for_user)):
        if shop.platform.value != platform_name:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Catalog for this shop type is managed automatically (Platform: {shop.platform.value})",
            )
        return shop
    return platform_checker
