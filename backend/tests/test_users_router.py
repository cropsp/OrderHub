"""USERS-LIST-500 — GET /api/users must exclude the persistent system user.

Root cause (prod): the system user row (SYSTEM_USER_ID) has
email='system@orderhub.local'. UserResponse.email is EmailStr, and pydantic's
email-validator rejects '.local' as a reserved/special-use TLD (RFC 6761), so
serializing that row raised ValidationError and 500'd the whole list endpoint.

Fix: list_users filters the system user out at the query level. The system row
is an internal audit principal (webhook/scheduler actor), never a team member.

The codebase has no real-DB test fixture (every backend/tests/*.py mocks the
AsyncSession), so we (a) capture the issued statement and assert the WHERE
excludes SYSTEM_USER_ID, and (b) assert directly that UserResponse rejects the
system row's shape — documenting *why* the filter must exist.
"""
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql

from constants import SYSTEM_USER_ID
from models.user import UserRole
from routers.users import list_users
from schemas.user import UserResponse


@pytest.mark.asyncio
async def test_list_users_excludes_system_user():
    """The list query must filter out SYSTEM_USER_ID so its unserializable
    reserved-TLD email never reaches UserResponse."""
    captured = []

    async def fake_execute(stmt):
        captured.append(stmt)
        r = MagicMock()
        r.scalars.return_value.all.return_value = []
        return r

    db = MagicMock()
    db.execute = AsyncMock(side_effect=fake_execute)

    current_user = MagicMock()
    current_user.role = UserRole.OWNER

    await list_users(current_user=current_user, db=db)

    assert captured, "list_users issued no query"
    sql = str(
        captured[0].compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    ).lower()
    assert str(SYSTEM_USER_ID) in sql and "!=" in sql, (
        "list_users query does not exclude the system user. "
        f"Compiled SQL: {sql}"
    )


def test_user_response_rejects_system_user_email():
    """Documents the offending shape: the system user's reserved-TLD email is
    not a valid EmailStr, so UserResponse cannot serialize that row — which is
    precisely why list_users must exclude it."""
    system_row = {
        "id": SYSTEM_USER_ID,
        "email": "system@orderhub.local",
        "full_name": "System (webhooks/scheduler)",
        "role": UserRole.OWNER,
        "is_active": False,
        "preferences": {},
        "created_at": "2026-04-25T16:00:00Z",
        "updated_at": "2026-04-25T16:00:00Z",
    }
    with pytest.raises(ValidationError):
        UserResponse.model_validate(system_row)
