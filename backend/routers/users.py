"""
OrderHub CRM — Users Router

User management (owner only): list, create, update.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from constants import SYSTEM_USER_ID
from database import get_db
from models.order import Order
from models.shop import Shop
from models.user import User, UserRole
from schemas.user import (
    UserCreate, UserUpdate, UserResponse, UserWithPasswordResponse,
    UserPreferencesUpdate, ShopAccessResponse, ShopAccessUpdate,
)
from routers.dependencies import get_current_user, require_role
from services import access_service
from services.auth_service import hash_password, generate_temp_password
from services.order_service import get_order_detail, update_order
from schemas.order import OrderUpdate

router = APIRouter(prefix="/api/users", tags=["users"])


async def _load_manageable_user(db: AsyncSession, user_id: uuid.UUID) -> User:
    """Load a non-system user or raise 404 (shop-access endpoints)."""
    if user_id == SYSTEM_USER_ID:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


async def _active_shop_ids(db: AsyncSession) -> list[uuid.UUID]:
    result = await db.execute(select(Shop.id).where(Shop.is_active == True))  # noqa: E712
    return list(result.scalars().all())


@router.get("", response_model=list[UserResponse])
async def list_users(
    current_user: User = Depends(require_role(UserRole.OWNER)),
    db: AsyncSession = Depends(get_db),
):
    """List all users (owner only).

    Excludes the persistent system user (SYSTEM_USER_ID) — it's an internal
    audit principal for webhook/scheduler rows, never a team member, and its
    reserved-TLD email (system@orderhub.local) is not a valid EmailStr, so
    including it would fail UserResponse serialization.
    """
    result = await db.execute(
        select(User)
        .where(User.id != SYSTEM_USER_ID)
        .order_by(User.created_at.desc())
    )
    return result.scalars().all()


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """Get current user profile."""
    return current_user


@router.patch("/me/preferences", response_model=UserResponse)
async def update_preferences(
    body: UserPreferencesUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update current user Preferences (timezone, refresh intervals, etc)."""
    current_user.preferences = body.preferences
    await db.flush()
    await db.refresh(current_user)
    return current_user


@router.post("", response_model=UserWithPasswordResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreate,
    current_user: User = Depends(require_role(UserRole.OWNER)),
    db: AsyncSession = Depends(get_db),
):
    """Create a new user with auto-generated temporary password (owner only)."""
    # Check for duplicate email
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User with this email already exists",
        )

    temp_password = generate_temp_password()

    user = User(
        email=body.email,
        full_name=body.full_name,
        role=body.role,
        hashed_password=hash_password(temp_password),
        is_active=True,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)

    # USER-ACCESS-1 (rule 2): set initial shop access at creation so a new
    # MANAGER/DESIGNER is not trapped with zero visibility.
    await access_service.default_grants_for_new_user(
        db, user, body.shop_ids, actor_id=current_user.id
    )

    # Return the response with temp password (shown only once)
    response_data = UserResponse.model_validate(user).model_dump()
    response_data["temporary_password"] = temp_password
    return UserWithPasswordResponse(**response_data)


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: uuid.UUID,
    body: UserUpdate,
    current_user: User = Depends(require_role(UserRole.OWNER)),
    db: AsyncSession = Depends(get_db),
):
    """Update user role or active status (owner only)."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Prevent deactivating self
    if body.is_active is False and user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Cannot deactivate yourself",
        )

    # Prevent deactivating or demoting the last active owner
    is_removing_owner = (
        (body.is_active is False and user.role == UserRole.OWNER)
        or (body.role is not None and body.role != UserRole.OWNER and user.role == UserRole.OWNER)
    )
    if is_removing_owner:
        count_result = await db.execute(
            select(func.count())
            .select_from(User)
            .where(User.role == UserRole.OWNER, User.is_active == True, User.id != user_id)
        )
        if count_result.scalar() == 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Cannot remove the last active owner",
            )

    # Apply updates
    if body.full_name is not None:
        user.full_name = body.full_name
    if body.role is not None:
        user.role = body.role
    if body.is_active is not None:
        user.is_active = body.is_active

    await db.flush()
    await db.refresh(user)
    return user


# ─── Shop access (USER-ACCESS-1) ───────────────────────────

@router.get("/{user_id}/shop-access", response_model=ShopAccessResponse)
async def get_user_shop_access(
    user_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.OWNER)),
    db: AsyncSession = Depends(get_db),
):
    """The shops a user can access (owner only).

    OWNER targets are unrestricted — reported as every active shop so the editor
    reflects reality (and is shown disabled).
    """
    user = await _load_manageable_user(db, user_id)
    if user.role == UserRole.OWNER:
        return ShopAccessResponse(shop_ids=await _active_shop_ids(db))
    granted = await access_service.get_granted_shop_ids(db, user_id)
    return ShopAccessResponse(shop_ids=list(granted))


@router.put("/{user_id}/shop-access", response_model=ShopAccessResponse)
async def set_user_shop_access(
    user_id: uuid.UUID,
    body: ShopAccessUpdate,
    current_user: User = Depends(require_role(UserRole.OWNER)),
    db: AsyncSession = Depends(get_db),
):
    """Replace a user's shop grants (owner only).

    OWNER targets are a no-op (unrestricted). Revoking a shop from a DESIGNER who
    still has assigned orders there is refused with 409 unless `unassign_orders`
    is set — in which case those orders are unassigned (audited) before the grant
    is removed, so revocation actually removes visibility of that shop's PII.
    """
    user = await _load_manageable_user(db, user_id)
    if user.role == UserRole.OWNER:
        # Unrestricted by design — ignore and report the full set.
        return ShopAccessResponse(shop_ids=await _active_shop_ids(db))

    desired = set(body.shop_ids)
    current = await access_service.get_granted_shop_ids(db, user_id)
    removed = current - desired

    # Which revoked shops still have orders assigned to this user?
    blocked: list[dict] = []
    if removed:
        count_rows = await db.execute(
            select(Order.shop_id, func.count())
            .where(
                Order.assigned_designer_id == user_id,
                Order.shop_id.in_(removed),
            )
            .group_by(Order.shop_id)
        )
        blocked = [
            {"shop_id": str(shop_id), "assigned_order_count": count}
            for shop_id, count in count_rows.all()
            if count > 0
        ]

    if blocked and not body.unassign_orders:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "User still has assigned orders in shops being revoked.",
                "blocked": blocked,
            },
        )

    # Confirmed: unassign the user's orders in every revoked shop (audited path).
    if blocked and body.unassign_orders:
        revoked_shop_ids = {uuid.UUID(b["shop_id"]) for b in blocked}
        order_rows = await db.execute(
            select(Order.id).where(
                Order.assigned_designer_id == user_id,
                Order.shop_id.in_(revoked_shop_ids),
            )
        )
        for (order_id,) in order_rows.all():
            order = await get_order_detail(db, order_id)
            if order is not None:
                await update_order(
                    db, order, OrderUpdate(assigned_designer_id=None), current_user
                )

    await access_service.set_shop_access(
        db, user_id, desired, actor_id=current_user.id
    )
    await db.flush()

    granted = await access_service.get_granted_shop_ids(db, user_id)
    return ShopAccessResponse(shop_ids=list(granted))
