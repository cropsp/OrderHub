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
    Currently assumes any active user can access any shop (to be refined if multiple tenants added).
    """
    from models.shop import Shop
    from sqlalchemy import select

    result = await db.execute(select(Shop).filter(Shop.id == shop_id))
    shop = result.scalar_one_or_none()

    if not shop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shop not found",
        )

    # Ownership check: shop.owner_id should match current_user.id or user must be ADMIN/OWNER
    # For now, we trust get_current_user and check if shop exists.
    # TODO: Implement strict multi-tenant ownership check if needed.

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
