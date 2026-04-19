"""
OrderHub CRM — Users Router

User management (owner only): list, create, update.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.user import User, UserRole
from schemas.user import UserCreate, UserUpdate, UserResponse, UserWithPasswordResponse
from routers.dependencies import get_current_user, require_role
from services.auth_service import hash_password, generate_temp_password

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("", response_model=list[UserResponse])
async def list_users(
    current_user: User = Depends(require_role(UserRole.OWNER)),
    db: AsyncSession = Depends(get_db),
):
    """List all users (owner only)."""
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    return result.scalars().all()


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
