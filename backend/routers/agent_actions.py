"""
OrderHub CRM — Agent Action Log Router (MCP-WAREHOUSE §5.8)

Two endpoints:
  - POST /api/agent-actions  — the MCP server reports one action it performed.
  - GET  /api/agent-actions  — the owner reviews what the agent has been doing.

The actor is always taken from the access token, never from the body: an agent
cannot attribute its work to someone else.

Reporting is a *record* of an action that already happened, not an
authorization step. It deliberately does not re-check anything — the write it
describes was already allowed (or denied) by the real endpoint's own guards.
"""

import json
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.agent_action_log import AgentActionLog
from models.user import User, UserRole
from routers.dependencies import get_current_user, require_role
from schemas.agent_action import AgentActionCreate, AgentActionRead

router = APIRouter(prefix="/api/agent-actions", tags=["Agent Actions"])

# Arguments are an intent record, not a payload store. A tool call that needs
# more than this is misusing the log.
MAX_ARGUMENTS_BYTES = 16_384


@router.post("", response_model=AgentActionRead, status_code=status.HTTP_201_CREATED)
async def report_agent_action(
    body: AgentActionCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Record one action taken by an AI agent on the caller's behalf.

    Open to any authenticated caller, but only ever for themselves — `actor_id`
    comes from the token. Failed actions are recorded too (`ok=false`), because a
    repeated 403 or validation error is exactly what an operator wants to see.
    """
    if len(json.dumps(body.arguments, default=str)) > MAX_ARGUMENTS_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                f"arguments exceed {MAX_ARGUMENTS_BYTES} bytes; the action log "
                "records intent, not payloads"
            ),
        )

    entry = AgentActionLog(
        actor_id=user.id,
        tool=body.tool,
        arguments=body.arguments,
        ok=body.ok,
        object_type=body.object_type,
        object_id=body.object_id,
        summary=body.summary,
        error=body.error,
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)

    result = AgentActionRead.model_validate(entry)
    result.actor_email = user.email
    return result


@router.get("", response_model=List[AgentActionRead])
async def list_agent_actions(
    actor_id: Optional[uuid.UUID] = Query(None),
    tool: Optional[str] = Query(None, max_length=64),
    ok: Optional[bool] = Query(None),
    object_id: Optional[str] = Query(None, max_length=64),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.OWNER)),
):
    """Review agent activity, newest first.

    OWNER-only: this is the oversight surface for what an automated principal has
    been doing, and the agent itself has no reason to read it.
    """
    stmt = (
        select(AgentActionLog, User.email)
        .join(User, User.id == AgentActionLog.actor_id)
        .order_by(AgentActionLog.created_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    if actor_id is not None:
        stmt = stmt.where(AgentActionLog.actor_id == actor_id)
    if tool is not None:
        stmt = stmt.where(AgentActionLog.tool == tool)
    if ok is not None:
        stmt = stmt.where(AgentActionLog.ok == ok)
    if object_id is not None:
        stmt = stmt.where(AgentActionLog.object_id == object_id)

    result = await db.execute(stmt)
    entries = []
    for entry, email in result.all():
        read = AgentActionRead.model_validate(entry)
        read.actor_email = email
        entries.append(read)
    return entries
