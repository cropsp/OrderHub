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


async def assert_shop_access(
    db: AsyncSession,
    shop_id: uuid.UUID,
    current_user: User,
) -> None:
    """Guard: 404 if the shop is missing, 403 if the caller may not see it.

    The single shop-scope gate (USER-ACCESS-1). Access is by explicit grant
    (`user_shop_access`); OWNER is unrestricted. 403-not-404 for a known shop the
    caller can't see is intentional and consistent (shop ids are unguessable
    UUIDs and list_shops already hides them).
    """
    from models.shop import Shop
    from sqlalchemy import select
    from services.access_service import get_shop_scope

    result = await db.execute(select(Shop.id).where(Shop.id == shop_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shop not found",
        )

    scope = await get_shop_scope(db, current_user)
    if not scope.can_access(shop_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this shop",
        )


async def assert_order_access(
    db: AsyncSession,
    order,
    current_user: User,
) -> None:
    """Guard for order-scoped surfaces (USER-ACCESS-1).

    OWNER: unrestricted. DESIGNER: assignment wins — visible iff assigned to them
    (the assignment auto-grants shop access, so shop-level surfaces stay coherent).
    MANAGER: scoped by shop grant on the order's shop.
    """
    if current_user.role == UserRole.OWNER:
        return

    if current_user.role == UserRole.DESIGNER:
        if order.assigned_designer_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not assigned to this order",
            )
        return

    from services.access_service import get_shop_scope

    scope = await get_shop_scope(db, current_user)
    if not scope.can_access(order.shop_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this shop",
        )


async def get_shop_for_user(
    shop_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Fetch a shop and verify the current user has access to it.

    Owner: any shop (unrestricted). Manager/Designer: only shops explicitly
    granted via `user_shop_access` (USER-ACCESS-1). A designer's shop access is
    materialised when an order in that shop is assigned to them.
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

    from services.access_service import get_shop_scope

    scope = await get_shop_scope(db, current_user)
    if not scope.can_access(shop_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this shop",
        )

    return shop


async def require_shop_access(
    shop_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> User:
    """Router/route-level dependency form of assert_shop_access for endpoints
    that carry `shop_id` in the path (USER-ACCESS-1)."""
    await assert_shop_access(db, shop_id, current_user)
    return current_user


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
