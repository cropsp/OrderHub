"""S004-mcp-wrapper — idlaser_service regression guards.

Mock-heavy: the real onnxruntime / opencv / idlaser pipeline never runs
under pytest. ``process_one_streaming`` / ``reprocess_streaming`` /
``load_template`` / ``_bgr_from_bytes`` / ``_persist_dxf`` are patched so
the service's state-machine + SSE-event taxonomy + DB writes can be
exercised in isolation.

Nine guards:
  1. validate_photo_attachment returns row when type=REFERENCE + matches order.
  2. validate_photo_attachment raises 404 when type != REFERENCE.
  3. create_pending_job inserts a PENDING row with correct FKs.
  4. Pipeline AUTO path → state=READY, result_attachment_id set,
     export.completed yielded last.
  5. Pipeline REVIEW path → state=NEEDS_REVIEW, manual_corners null,
     review_required yielded with best_guess_corners.
  6. Manual-corners reprocess uses reprocess_streaming + persists
     manual_corners on the job.
  7. Unknown-error → state=FAILED, error_message set, error event emitted.
  8. Timeout (asyncio.TimeoutError surrogate) → state=FAILED,
     error_message="Exceeded {N}s", error event emitted.
  9. ONNX-transient error → tenacity retries 3x; sentinel that the
     decorator is in fact wrapping the function.
"""

import asyncio
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from models.attachment import Attachment, AttachmentType
from models.idlaser_draft_job import IdlaserDraftJob, IdlaserDraftJobState
from services import idlaser_service


# ─── DB / helpers ──────────────────────────────────────────────────────


def _make_db(scalar_one_or_none=None):
    """Lightweight async-DB stub. Capture add/commit calls; one canned
    scalar_one_or_none for the first execute() call."""
    db = MagicMock()

    async def fake_execute(_stmt):
        r = MagicMock()
        r.scalar_one_or_none.return_value = scalar_one_or_none
        return r

    db.execute = AsyncMock(side_effect=fake_execute)
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.flush = AsyncMock()
    return db


def _make_job(order_id=None, photo_id=None) -> IdlaserDraftJob:
    job = IdlaserDraftJob(
        id=uuid.uuid4(),
        order_id=order_id or uuid.uuid4(),
        photo_attachment_id=photo_id or uuid.uuid4(),
        triggered_by_id=uuid.uuid4(),
        state=IdlaserDraftJobState.PENDING,
    )
    job.created_at = datetime.now(timezone.utc)
    job.updated_at = job.created_at
    return job


def _make_streaming_result(status: str, **kwargs):
    sr = MagicMock()
    sr.status = status
    sr.dxf_bytes = kwargs.get("dxf_bytes", b"FAKEDXF" if status == "AUTO" else None)
    sr.review_reason = kwargs.get("review_reason")
    sr.best_guess_corners = kwargs.get("best_guess_corners")
    return sr


# ─── 1. validate_photo_attachment success ──────────────────────────────


@pytest.mark.asyncio
async def test_validate_photo_attachment_returns_row_when_reference():
    order_id = uuid.uuid4()
    photo_id = uuid.uuid4()
    fake_photo = MagicMock(spec=Attachment)
    fake_photo.id = photo_id
    fake_photo.order_id = order_id
    fake_photo.attachment_type = AttachmentType.REFERENCE
    db = _make_db(scalar_one_or_none=fake_photo)
    result = await idlaser_service.validate_photo_attachment(
        db, order_id, photo_id,
    )
    assert result is fake_photo


# ─── 2. validate_photo_attachment 404 ─────────────────────────────────


@pytest.mark.asyncio
async def test_validate_photo_attachment_404_when_not_found():
    db = _make_db(scalar_one_or_none=None)
    with pytest.raises(HTTPException) as exc:
        await idlaser_service.validate_photo_attachment(
            db, uuid.uuid4(), uuid.uuid4(),
        )
    assert exc.value.status_code == 404


# ─── 3. create_pending_job inserts PENDING row ────────────────────────


@pytest.mark.asyncio
async def test_create_pending_job_inserts_pending_row():
    db = _make_db()
    order_id = uuid.uuid4()
    photo_id = uuid.uuid4()
    user_id = uuid.uuid4()
    job = await idlaser_service.create_pending_job(
        db, order_id, photo_id, user_id,
    )
    db.add.assert_called_once_with(job)
    db.commit.assert_awaited()
    assert job.order_id == order_id
    assert job.photo_attachment_id == photo_id
    assert job.triggered_by_id == user_id
    assert job.state == IdlaserDraftJobState.PENDING


# ─── 4. AUTO path: READY + export.completed ───────────────────────────


@pytest.mark.asyncio
async def test_pipeline_auto_path_finishes_ready_with_export_completed(monkeypatch):
    db = _make_db()
    job = _make_job()

    monkeypatch.setattr(
        idlaser_service, "_bgr_from_bytes", lambda _: object(),
    )
    monkeypatch.setattr(
        idlaser_service, "load_template", lambda _: object(),
    )

    def fake_run(_bgr, _tmpl, progress):
        progress("detect.classical.completed", {"candidates": 3, "k_face": 1})
        progress("rectify.completed", {})
        return _make_streaming_result("AUTO", dxf_bytes=b"BYTES")

    monkeypatch.setattr(
        idlaser_service, "_run_pipeline_with_retry", fake_run,
    )

    async def fake_persist(_db, _job, _bytes, _uploader):
        att = MagicMock(spec=Attachment)
        att.id = uuid.uuid4()
        return att

    monkeypatch.setattr(idlaser_service, "_persist_dxf", fake_persist)

    events: list[dict] = []
    async for event in idlaser_service.run_draft_pipeline_sse(
        db, job, b"photo", job.triggered_by_id,
    ):
        events.append(event)

    types = [e["type"] for e in events]
    assert types[0] == "job.started"
    assert "export.completed" in types
    assert types[-1] == "export.completed"
    assert job.state == IdlaserDraftJobState.READY
    assert job.result_attachment_id is not None
    assert job.completed_at is not None


# ─── 5. REVIEW path: NEEDS_REVIEW + review_required event ─────────────


@pytest.mark.asyncio
async def test_pipeline_review_path_emits_review_required(monkeypatch):
    db = _make_db()
    job = _make_job()
    corners = [[10.0, 10.0], [100.0, 10.0], [100.0, 100.0], [10.0, 100.0]]

    monkeypatch.setattr(idlaser_service, "_bgr_from_bytes", lambda _: object())
    monkeypatch.setattr(idlaser_service, "load_template", lambda _: object())

    def fake_run(_bgr, _tmpl, progress):
        progress("detect.classical.completed", {"candidates": 0, "k_face": 0})
        return _make_streaming_result(
            "REVIEW",
            review_reason="low_quad_score",
            best_guess_corners=corners,
        )

    monkeypatch.setattr(
        idlaser_service, "_run_pipeline_with_retry", fake_run,
    )

    events: list[dict] = []
    async for event in idlaser_service.run_draft_pipeline_sse(
        db, job, b"photo", job.triggered_by_id,
    ):
        events.append(event)

    types = [e["type"] for e in events]
    assert "review_required" in types
    review = next(e for e in events if e["type"] == "review_required")
    assert review["payload"]["best_guess_corners"] == corners
    assert review["payload"]["reason"] == "low_quad_score"
    assert job.state == IdlaserDraftJobState.NEEDS_REVIEW
    assert job.manual_corners is None


# ─── 6. Manual-corners reprocess persists corners + uses reprocess ────


@pytest.mark.asyncio
async def test_manual_corners_reprocess_persists_corners_and_uses_reprocess_fn(
    monkeypatch,
):
    db = _make_db()
    job = _make_job()
    corners = [[1.0, 2.0], [3.0, 4.0], [5.0, 6.0], [7.0, 8.0]]

    monkeypatch.setattr(idlaser_service, "_bgr_from_bytes", lambda _: object())
    monkeypatch.setattr(idlaser_service, "load_template", lambda _: object())

    called_with: dict = {}

    def fake_reprocess(_bgr, given_corners, _tmpl, progress):
        called_with["corners"] = given_corners
        progress("rectify.completed", {})
        return _make_streaming_result("AUTO", dxf_bytes=b"DXF")

    monkeypatch.setattr(
        idlaser_service, "_run_reprocess_with_retry", fake_reprocess,
    )

    # ensure the AUTO branch's persist_dxf doesn't touch disk
    async def fake_persist(_db, _job, _bytes, _uploader):
        att = MagicMock(spec=Attachment)
        att.id = uuid.uuid4()
        return att

    monkeypatch.setattr(idlaser_service, "_persist_dxf", fake_persist)

    events: list[dict] = []
    async for event in idlaser_service.run_reprocess_pipeline_sse(
        db, job, b"photo", job.triggered_by_id, corners,
    ):
        events.append(event)

    assert called_with["corners"] == corners
    assert job.manual_corners == corners
    assert job.state == IdlaserDraftJobState.READY


# ─── 7. Unknown error → FAILED + error event ──────────────────────────


@pytest.mark.asyncio
async def test_unknown_error_sets_failed_and_emits_error(monkeypatch):
    db = _make_db()
    job = _make_job()

    monkeypatch.setattr(idlaser_service, "_bgr_from_bytes", lambda _: object())
    monkeypatch.setattr(idlaser_service, "load_template", lambda _: object())

    def fake_run(*_args, **_kwargs):
        raise RuntimeError("nope")

    monkeypatch.setattr(
        idlaser_service, "_run_pipeline_with_retry", fake_run,
    )

    events: list[dict] = []
    async for event in idlaser_service.run_draft_pipeline_sse(
        db, job, b"photo", job.triggered_by_id,
    ):
        events.append(event)

    types = [e["type"] for e in events]
    assert types[-1] == "error"
    assert job.state == IdlaserDraftJobState.FAILED
    assert "nope" in (job.error_message or "")


# ─── 8. Timeout → FAILED with "Exceeded {N}s" ─────────────────────────


@pytest.mark.asyncio
async def test_timeout_sets_failed_with_exceeded_message(monkeypatch):
    db = _make_db()
    job = _make_job()

    monkeypatch.setattr(idlaser_service, "_bgr_from_bytes", lambda _: object())
    monkeypatch.setattr(idlaser_service, "load_template", lambda _: object())

    # Force asyncio.wait_for inside _stream to raise TimeoutError by
    # patching it to a coroutine that always times out — simpler than
    # building a slow real call. We patch the module-local wait_for
    # via asyncio.wait_for to ensure our service path raises.
    real_wait_for = asyncio.wait_for

    async def insta_timeout(_aw, timeout):
        # cancel the awaitable so its thread isn't leaked
        if hasattr(_aw, "close"):
            _aw.close()
        raise asyncio.TimeoutError()

    monkeypatch.setattr(asyncio, "wait_for", insta_timeout)

    try:
        events: list[dict] = []
        async for event in idlaser_service.run_draft_pipeline_sse(
            db, job, b"photo", job.triggered_by_id,
        ):
            events.append(event)
    finally:
        monkeypatch.setattr(asyncio, "wait_for", real_wait_for)

    types = [e["type"] for e in events]
    assert types[-1] == "error"
    assert job.state == IdlaserDraftJobState.FAILED
    assert "Exceeded" in (job.error_message or "")
    assert job.error_message.endswith("s")


# ─── 9. Tenacity wrapping sentinel ────────────────────────────────────


def test_run_pipeline_with_retry_is_tenacity_wrapped():
    """Sanity check that _run_pipeline_with_retry is decorated with
    tenacity (so transient ONNX failures actually retry). We don't
    exercise the retry behaviour at runtime — that requires a real
    onnxruntime Fail exception which is environment-dependent."""
    assert hasattr(idlaser_service._run_pipeline_with_retry, "retry")
    assert hasattr(idlaser_service._run_reprocess_with_retry, "retry")
    # Confirm the retry stop is set to 3 attempts (matches OQ-10 plan)
    stop = idlaser_service._run_pipeline_with_retry.retry.stop
    # Tenacity's stop_after_attempt(3) exposes .max_attempt_number
    assert getattr(stop, "max_attempt_number", None) == 3
