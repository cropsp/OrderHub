"""S004-mcp-wrapper — idlaser router regression guards.

Mock-based, no real SSE transport. The router functions are invoked
directly with stubbed dependencies; we assert on the wiring (which
service functions are called, with which arguments) and on the auth
gate. The SSE event taxonomy itself is covered in
test_idlaser_service.py — this file only verifies that the router
plumbs the service correctly.

Five guards:
  1. _ensure_order_access raises 403 for DESIGNER not assigned to the order.
  2. _ensure_order_access allows DESIGNER assigned to the order and
     OWNER / MANAGER unconditionally.
  3. generate_draft validates photo + creates pending job + invokes the
     service's run_draft_pipeline_sse.
  4. submit_manual_corners requires job.photo_attachment_id to still exist
     (409 when null after operator deleted the photo).
  5. get_draft_job_status returns the job row after the access gate passes.
"""

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from models.idlaser_draft_job import IdlaserDraftJob, IdlaserDraftJobState
from models.user import UserRole
from routers import idlaser as router_module
from schemas.idlaser_draft_job import (
    IdlaserDraftJobCreate,
    ManualCornersRequest,
)


def _make_user(role: UserRole):
    user = MagicMock()
    user.id = uuid.uuid4()
    user.role = role
    return user


def _make_order(order_id, assigned_designer_id=None):
    order = MagicMock()
    order.id = order_id
    order.assigned_designer_id = assigned_designer_id
    return order


def _make_db(order=None):
    db = MagicMock()

    async def fake_execute(_stmt):
        r = MagicMock()
        r.scalar_one_or_none.return_value = order
        return r

    db.execute = AsyncMock(side_effect=fake_execute)
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    return db


# ─── 1. Designer not assigned → 403 ────────────────────────────────────


@pytest.mark.asyncio
async def test_ensure_order_access_blocks_unassigned_designer():
    order_id = uuid.uuid4()
    user = _make_user(UserRole.DESIGNER)
    order = _make_order(order_id, assigned_designer_id=uuid.uuid4())  # someone else
    db = _make_db(order)
    with pytest.raises(HTTPException) as exc:
        await router_module._ensure_order_access(db, order_id, user)
    assert exc.value.status_code == 403


# ─── 2. Designer assigned, OWNER, MANAGER → allowed ───────────────────


@pytest.mark.asyncio
async def test_ensure_order_access_allows_assigned_designer_and_managers():
    order_id = uuid.uuid4()
    designer = _make_user(UserRole.DESIGNER)
    order_for_designer = _make_order(order_id, assigned_designer_id=designer.id)
    db1 = _make_db(order_for_designer)
    result = await router_module._ensure_order_access(db1, order_id, designer)
    assert result is order_for_designer

    for role in (UserRole.OWNER, UserRole.MANAGER):
        manager = _make_user(role)
        any_order = _make_order(order_id, assigned_designer_id=None)
        db = _make_db(any_order)
        result = await router_module._ensure_order_access(db, order_id, manager)
        assert result is any_order


# ─── 3. generate_draft wires service correctly ────────────────────────


@pytest.mark.asyncio
async def test_generate_draft_validates_photo_and_creates_job(monkeypatch):
    order_id = uuid.uuid4()
    photo_id = uuid.uuid4()
    user = _make_user(UserRole.MANAGER)
    order = _make_order(order_id)
    db = _make_db(order)

    fake_photo = MagicMock()
    fake_photo.id = photo_id

    fake_job = MagicMock(spec=IdlaserDraftJob)
    fake_job.id = uuid.uuid4()
    fake_job.order_id = order_id

    validate = AsyncMock(return_value=fake_photo)
    create = AsyncMock(return_value=fake_job)
    read_bytes = AsyncMock(return_value=b"PHOTOBYTES")

    async def fake_run(job, photo_bytes, uploader_id):
        yield {
            "type": "job.started",
            "payload": {},
            "timestamp": "2026-05-19T00:00:00Z",
            "job_state": "running",
        }
        yield {
            "type": "export.completed",
            "payload": {"result_attachment_id": str(uuid.uuid4())},
            "timestamp": "2026-05-19T00:00:01Z",
            "job_state": "ready",
        }

    monkeypatch.setattr(router_module.idlaser_service, "validate_photo_attachment", validate)
    monkeypatch.setattr(router_module.idlaser_service, "create_pending_job", create)
    monkeypatch.setattr(router_module.idlaser_service, "_read_photo_bytes", read_bytes)
    monkeypatch.setattr(router_module.idlaser_service, "run_draft_pipeline_sse", fake_run)

    body = IdlaserDraftJobCreate(photo_attachment_id=photo_id)
    response = await router_module.generate_draft(
        order_id=order_id, body=body, current_user=user, db=db,
    )

    validate.assert_awaited_once()
    create.assert_awaited_once()
    read_bytes.assert_awaited_once()

    # Drain the SSE generator to verify event shape (sse_starlette format).
    sent = [chunk async for chunk in response.body_iterator]
    types = [chunk["event"] for chunk in sent]
    assert "job.started" in types
    assert "export.completed" in types
    # Each chunk's data is JSON-encoded
    parsed = json.loads(sent[0]["data"])
    assert "payload" in parsed and "timestamp" in parsed and "job_state" in parsed


# ─── 3b. generate_draft does NOT create PENDING row when file missing ─


@pytest.mark.asyncio
async def test_generate_draft_no_pending_row_when_photo_file_missing(monkeypatch):
    """File-on-disk validation precedes create_pending_job. A
    `_read_photo_bytes` failure must return 4xx without ever calling
    `create_pending_job` (no stranded PENDING rows in DB)."""
    order_id = uuid.uuid4()
    photo_id = uuid.uuid4()
    user = _make_user(UserRole.MANAGER)
    order = _make_order(order_id)
    db = _make_db(order)

    fake_photo = MagicMock()
    fake_photo.id = photo_id

    validate = AsyncMock(return_value=fake_photo)
    create = AsyncMock()  # must NOT be called
    read_bytes = AsyncMock(
        side_effect=HTTPException(status_code=404, detail="Photo file missing on disk")
    )

    monkeypatch.setattr(router_module.idlaser_service, "validate_photo_attachment", validate)
    monkeypatch.setattr(router_module.idlaser_service, "create_pending_job", create)
    monkeypatch.setattr(router_module.idlaser_service, "_read_photo_bytes", read_bytes)

    body = IdlaserDraftJobCreate(photo_attachment_id=photo_id)
    with pytest.raises(HTTPException) as exc:
        await router_module.generate_draft(
            order_id=order_id, body=body, current_user=user, db=db,
        )
    assert exc.value.status_code == 404
    validate.assert_awaited_once()
    read_bytes.assert_awaited_once()
    create.assert_not_awaited()  # ← key invariant: no stranded PENDING row


# ─── 4. manual-corners refuses when photo deleted ─────────────────────


@pytest.mark.asyncio
async def test_manual_corners_409_when_photo_attachment_deleted(monkeypatch):
    order_id = uuid.uuid4()
    job_id = uuid.uuid4()
    user = _make_user(UserRole.MANAGER)
    order = _make_order(order_id)
    db = _make_db(order)

    fake_job = MagicMock(spec=IdlaserDraftJob)
    fake_job.id = job_id
    fake_job.order_id = order_id
    fake_job.photo_attachment_id = None  # operator deleted the photo

    monkeypatch.setattr(
        router_module.idlaser_service,
        "get_job",
        AsyncMock(return_value=fake_job),
    )

    body = ManualCornersRequest(
        corners=[[1, 1], [2, 1], [2, 2], [1, 2]],
    )
    with pytest.raises(HTTPException) as exc:
        await router_module.submit_manual_corners(
            order_id=order_id, job_id=job_id, body=body,
            current_user=user, db=db,
        )
    assert exc.value.status_code == 409


# ─── 5. status endpoint returns the job row ───────────────────────────


@pytest.mark.asyncio
async def test_status_endpoint_returns_job_after_access_gate(monkeypatch):
    order_id = uuid.uuid4()
    job_id = uuid.uuid4()
    user = _make_user(UserRole.OWNER)
    order = _make_order(order_id)
    db = _make_db(order)

    fake_job = MagicMock(spec=IdlaserDraftJob)
    fake_job.id = job_id
    fake_job.order_id = order_id
    fake_job.state = IdlaserDraftJobState.READY
    fake_job.result_attachment_id = uuid.uuid4()
    fake_job.error_message = None
    fake_job.started_at = datetime.now(timezone.utc)
    fake_job.completed_at = datetime.now(timezone.utc)

    monkeypatch.setattr(
        router_module.idlaser_service,
        "get_job",
        AsyncMock(return_value=fake_job),
    )

    result = await router_module.get_draft_job_status(
        order_id=order_id, job_id=job_id, current_user=user, db=db,
    )
    assert result is fake_job
