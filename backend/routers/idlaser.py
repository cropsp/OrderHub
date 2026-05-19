"""
OrderHub CRM — ID-Laser Draft Pipeline Router (S004-mcp-wrapper)

Three routes:
  - POST /api/orders/{order_id}/generate-draft        → SSE stream
  - POST /api/orders/{order_id}/draft-jobs/{job_id}/manual-corners → SSE stream
  - GET  /api/orders/{order_id}/draft-jobs/{job_id}/status         → JSON

Role gates (master rule 10): OWNER/MANAGER always; DESIGNER only when
they are this order's assigned_designer. Anonymous gets 401 via the
shared Depends chain.

First user-facing SSE endpoint in the codebase. Uses
``sse_starlette.EventSourceResponse`` (auto-heartbeat) rather than
``StreamingResponse(media_type="text/event-stream")`` (the latter is
used in ``routers/mcp.py`` for the MCP-protocol-specific transport and
is locked per CLAUDE.md gotcha).
"""

import json
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from database import get_db
from logger import get_logger
from models.idlaser_draft_job import IdlaserDraftJob
from models.order import Order
from models.user import User, UserRole
from routers.dependencies import get_current_user
from schemas.idlaser_draft_job import (
    DraftJobStatusResponse,
    IdlaserDraftJobCreate,
    ManualCornersRequest,
)
from services import idlaser_service

logger = get_logger("routers.idlaser")

router = APIRouter(prefix="/api/orders", tags=["idlaser"])


async def _ensure_order_access(
    db: AsyncSession,
    order_id: uuid.UUID,
    user: User,
) -> Order:
    """OWNER/MANAGER unconditional, DESIGNER only if assigned to this order."""
    result = await db.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    if user.role == UserRole.DESIGNER and order.assigned_designer_id != user.id:
        raise HTTPException(status_code=403, detail="Not assigned to this order")
    return order


async def _serialize(event: dict) -> dict:
    """sse_starlette consumes {event, data} dicts. Pack the type as the
    event name; JSON-encode the rest as the data field."""
    return {
        "event": event["type"],
        "data": json.dumps(
            {
                "payload": event.get("payload", {}),
                "timestamp": event.get("timestamp"),
                "job_state": event.get("job_state"),
            }
        ),
    }


@router.post("/{order_id}/generate-draft")
async def generate_draft(
    order_id: uuid.UUID,
    body: IdlaserDraftJobCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Kick off a new IdlaserDraftJob and stream pipeline progress as SSE."""
    await _ensure_order_access(db, order_id, current_user)
    photo = await idlaser_service.validate_photo_attachment(
        db, order_id, body.photo_attachment_id,
    )
    job = await idlaser_service.create_pending_job(
        db, order_id, body.photo_attachment_id, current_user.id,
    )
    photo_bytes = await idlaser_service._read_photo_bytes(photo)

    async def event_gen():
        async for ev in idlaser_service.run_draft_pipeline_sse(
            db, job, photo_bytes, current_user.id,
        ):
            yield await _serialize(ev)

    return EventSourceResponse(event_gen())


@router.post("/{order_id}/draft-jobs/{job_id}/manual-corners")
async def submit_manual_corners(
    order_id: uuid.UUID,
    job_id: uuid.UUID,
    body: ManualCornersRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Resume an existing job with manager-supplied 4 corners. Re-streams
    the post-detect subset of pipeline events."""
    await _ensure_order_access(db, order_id, current_user)
    job = await idlaser_service.get_job(db, order_id, job_id)
    if job.photo_attachment_id is None:
        raise HTTPException(
            status_code=409,
            detail="Original photo attachment was deleted; cannot reprocess",
        )
    photo = await idlaser_service.validate_photo_attachment(
        db, order_id, job.photo_attachment_id,
    )
    photo_bytes = await idlaser_service._read_photo_bytes(photo)

    async def event_gen():
        async for ev in idlaser_service.run_reprocess_pipeline_sse(
            db, job, photo_bytes, current_user.id, body.corners,
        ):
            yield await _serialize(ev)

    return EventSourceResponse(event_gen())


@router.get(
    "/{order_id}/draft-jobs/{job_id}/status",
    response_model=DraftJobStatusResponse,
)
async def get_draft_job_status(
    order_id: uuid.UUID,
    job_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> IdlaserDraftJob:
    """Polling fallback for clients without SSE; also useful in tests."""
    await _ensure_order_access(db, order_id, current_user)
    return await idlaser_service.get_job(db, order_id, job_id)
