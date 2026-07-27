"""MCP-WAREHOUSE §5.8 — agent action log.

Router functions awaited directly with mocked dependencies, matching
test_products_platform_gate.py / test_product_image.py (no TestClient fixtures
exist in this repo).
"""
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from models.user import UserRole
from routers.agent_actions import (
    MAX_ARGUMENTS_BYTES,
    list_agent_actions,
    report_agent_action,
)
from schemas.agent_action import AgentActionCreate


def _agent(uid=None):
    u = MagicMock()
    u.id = uid or uuid.uuid4()
    u.email = "agent@orderhub.dev"
    u.role = UserRole.MANAGER
    return u


def _db():
    """AsyncMock session whose .add is synchronous and .refresh is a no-op.

    `refresh` must leave the staged object untouched so the router's
    model_validate sees the values it just set.
    """
    db = AsyncMock()
    db.add = MagicMock()
    db.refresh = AsyncMock(side_effect=_stamp_defaults)
    return db


async def _stamp_defaults(entry):
    # Stand in for the server-side defaults Postgres would fill on flush.
    from datetime import datetime, timezone

    if getattr(entry, "id", None) is None:
        entry.id = uuid.uuid4()
    if getattr(entry, "created_at", None) is None:
        entry.created_at = datetime.now(timezone.utc)


def _payload(**over):
    body = dict(
        tool="record_material_receipt",
        arguments={"material_id": "m1", "qty": "25"},
        ok=True,
        object_type="material_receipt",
        object_id="r1",
        summary="+25 dm2 leather @ 597.14 UAH",
        error=None,
    )
    body.update(over)
    return AgentActionCreate(**body)


@pytest.mark.asyncio
async def test_actor_comes_from_the_token_not_the_body():
    """An agent must not be able to attribute its work to another user."""
    db, user = _db(), _agent()
    result = await report_agent_action(_payload(), db=db, user=user)

    staged = db.add.call_args[0][0]
    assert staged.actor_id == user.id
    assert result.actor_email == "agent@orderhub.dev"
    # AgentActionCreate has no actor field at all — nothing to forge.
    assert not hasattr(_payload(), "actor_id")


@pytest.mark.asyncio
async def test_records_intent_verbatim():
    db, user = _db(), _agent()
    await report_agent_action(_payload(), db=db, user=user)

    staged = db.add.call_args[0][0]
    assert staged.tool == "record_material_receipt"
    assert staged.arguments == {"material_id": "m1", "qty": "25"}
    assert staged.object_type == "material_receipt"
    assert staged.object_id == "r1"
    assert staged.summary == "+25 dm2 leather @ 597.14 UAH"
    assert db.commit.await_count == 1


@pytest.mark.asyncio
async def test_failed_action_is_recorded_with_its_error():
    """A repeated 403 or validation failure is exactly what the owner wants to see."""
    db, user = _db(), _agent()
    await report_agent_action(
        _payload(
            ok=False,
            object_id=None,
            summary=None,
            error="403: You do not have access to this shop",
        ),
        db=db,
        user=user,
    )

    staged = db.add.call_args[0][0]
    assert staged.ok is False
    assert "do not have access" in staged.error


@pytest.mark.asyncio
async def test_oversized_arguments_rejected():
    """The log records intent, not payloads."""
    db, user = _db(), _agent()
    fat = {"blob": "x" * (MAX_ARGUMENTS_BYTES + 100)}

    with pytest.raises(HTTPException) as exc:
        await report_agent_action(_payload(arguments=fat), db=db, user=user)

    assert exc.value.status_code == 413
    db.add.assert_not_called()
    db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_arguments_default_to_empty_dict():
    db, user = _db(), _agent()
    await report_agent_action(
        AgentActionCreate(tool="archive_material", ok=True), db=db, user=user
    )
    assert db.add.call_args[0][0].arguments == {}


@pytest.mark.asyncio
async def test_list_filters_compile_into_the_query():
    db = AsyncMock()
    db.execute.return_value = MagicMock(all=MagicMock(return_value=[]))
    owner = MagicMock(role=UserRole.OWNER, id=uuid.uuid4())

    await list_agent_actions(
        actor_id=uuid.uuid4(),
        tool="set_product_bom",
        ok=False,
        object_id="p1",
        page=2,
        limit=10,
        db=db,
        user=owner,
    )

    sql = str(db.execute.await_args[0][0].compile())
    assert "agent_action_log.tool = " in sql
    assert "agent_action_log.ok = " in sql
    assert "agent_action_log.object_id = " in sql
    assert "ORDER BY agent_action_log.created_at DESC" in sql


def test_list_is_owner_only():
    """Oversight surface: the agent itself has no reason to read it."""
    import inspect

    from routers.dependencies import require_role

    dep = inspect.signature(list_agent_actions).parameters["user"].default
    # require_role(OWNER) closes over `roles`; assert the closure holds only OWNER.
    roles = dep.dependency.__closure__[0].cell_contents
    assert roles == (UserRole.OWNER,)
    assert require_role is not None  # imported symbol is the one under test
