"""
OrderHub CRM — ID-Laser Draft Pipeline Service (S004-mcp-wrapper)

Wraps ``idlaser.api.process_one_streaming`` and ``reprocess_streaming``
behind an SSE-friendly async iterator. The synchronous pipeline runs in
``asyncio.to_thread``; its progress callback fires from inside that
worker thread and bridges into the asyncio event loop via
``loop.call_soon_threadsafe(queue.put_nowait, event)``.

Per S004 master rule 14 + rule 27, idlaser internals are off-limits —
only ``idlaser.api`` is imported.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator, Callable

import aiofiles
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from config import get_settings
from logger import get_logger
from models.attachment import Attachment, AttachmentType
from models.idlaser_draft_job import IdlaserDraftJob, IdlaserDraftJobState
from services.file_storage import UPLOADS_DIR

logger = get_logger("services.idlaser")
settings = get_settings()


# ─── idlaser surface (rule 27 — only via idlaser.api) ────────────────
# Wrapped: idlaser is installed inside the docker container at startup
# (entrypoint.sh: pip install -e /idlaser). For bare-metal pytest runs
# without idlaser on PYTHONPATH, the symbols stay as None and tests
# monkeypatch them.
try:
    from idlaser.api import (  # noqa: E402
        process_one_streaming,
        reprocess_streaming,
        StreamingResult,
        load_template,
    )
except ImportError:
    process_one_streaming = None  # type: ignore[assignment]
    reprocess_streaming = None  # type: ignore[assignment]
    StreamingResult = None  # type: ignore[assignment, misc]
    load_template = None  # type: ignore[assignment]


# ─── Transient-error retry surface (OQ-10) ───────────────────────────
try:
    import onnxruntime as _ort  # noqa: WPS433
    _ORT_FAIL: type[BaseException] = _ort.capi.onnxruntime_pybind11_state.Fail
except (ImportError, AttributeError):
    # ORT may be absent in CI/test envs; sentinel never raised in practice.
    class _OrtFailSentinel(Exception):
        """Placeholder when onnxruntime is unavailable."""

    _ORT_FAIL = _OrtFailSentinel

TRANSIENT_ML_ERRORS: tuple[type[BaseException], ...] = (_ORT_FAIL, OSError)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type(TRANSIENT_ML_ERRORS),
    reraise=True,
)
def _run_pipeline_with_retry(
    bgr,
    template,
    progress_cb: Callable[[str, dict], None],
) -> StreamingResult:
    """Tenacity wrapper. Retries the whole pipeline on transient ONNX
    session failures (`onnxruntime ... Fail`) or filesystem races
    (`OSError`) up to 3x with exponential backoff. REVIEW outcomes are
    NOT exceptions, so they bypass the retry; misalignment is the
    proper response, not a retry trigger.
    """
    return process_one_streaming(bgr, template, progress_cb)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type(TRANSIENT_ML_ERRORS),
    reraise=True,
)
def _run_reprocess_with_retry(
    bgr,
    corners: list[list[float]],
    template,
    progress_cb: Callable[[str, dict], None],
) -> StreamingResult:
    return reprocess_streaming(bgr, corners, template, progress_cb)


# ─── Photo / attachment helpers ──────────────────────────────────────


async def validate_photo_attachment(
    db: AsyncSession,
    order_id: uuid.UUID,
    photo_attachment_id: uuid.UUID,
) -> Attachment:
    """Confirm the photo attachment belongs to this order and is REFERENCE-typed."""
    result = await db.execute(
        select(Attachment).where(
            Attachment.id == photo_attachment_id,
            Attachment.order_id == order_id,
            Attachment.attachment_type == AttachmentType.REFERENCE,
        )
    )
    photo = result.scalar_one_or_none()
    if photo is None:
        raise HTTPException(
            status_code=404,
            detail="REFERENCE attachment not found on this order",
        )
    return photo


async def _read_photo_bytes(photo: Attachment) -> bytes:
    abs_path = (UPLOADS_DIR / photo.file_path).resolve()
    uploads_root = UPLOADS_DIR.resolve()
    if uploads_root not in abs_path.parents:
        raise HTTPException(status_code=404, detail="Photo file path invalid")
    if not abs_path.is_file():
        raise HTTPException(status_code=404, detail="Photo file missing on disk")
    async with aiofiles.open(abs_path, "rb") as fp:
        return await fp.read()


# ─── DB job helpers ──────────────────────────────────────────────────


async def create_pending_job(
    db: AsyncSession,
    order_id: uuid.UUID,
    photo_attachment_id: uuid.UUID,
    triggered_by_id: uuid.UUID,
) -> IdlaserDraftJob:
    """Insert a fresh PENDING job row."""
    job = IdlaserDraftJob(
        id=uuid.uuid4(),
        order_id=order_id,
        photo_attachment_id=photo_attachment_id,
        triggered_by_id=triggered_by_id,
        state=IdlaserDraftJobState.PENDING,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


async def get_job(
    db: AsyncSession,
    order_id: uuid.UUID,
    job_id: uuid.UUID,
) -> IdlaserDraftJob:
    result = await db.execute(
        select(IdlaserDraftJob).where(
            IdlaserDraftJob.id == job_id,
            IdlaserDraftJob.order_id == order_id,
        )
    )
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Draft job not found")
    return job


# ─── DXF persistence ─────────────────────────────────────────────────


async def _persist_dxf(
    db: AsyncSession,
    job: IdlaserDraftJob,
    dxf_bytes: bytes,
    uploader_id: uuid.UUID,
) -> Attachment:
    """Write DXF bytes to disk and create the result MOCKUP Attachment row."""
    order_dir = UPLOADS_DIR / str(job.order_id)
    order_dir.mkdir(parents=True, exist_ok=True)
    file_uuid = uuid.uuid4()
    file_name = f"draft_{job.id}.dxf"
    safe_filename = f"{file_uuid}_{file_name}"
    abs_path = order_dir / safe_filename
    relative_path = str(Path(str(job.order_id)) / safe_filename)

    async with aiofiles.open(abs_path, "wb") as fp:
        await fp.write(dxf_bytes)

    attachment = Attachment(
        id=uuid.uuid4(),
        order_id=job.order_id,
        uploaded_by_id=uploader_id,
        file_name=file_name,
        file_path=relative_path,
        file_size=len(dxf_bytes),
        mime_type="application/dxf",
        attachment_type=AttachmentType.MOCKUP,
    )
    db.add(attachment)
    await db.flush()
    return attachment


# ─── SSE bridge ──────────────────────────────────────────────────────


def _bgr_from_bytes(photo_bytes: bytes):
    """Decode JPEG/PNG bytes to OpenCV BGR ndarray. Imported lazily so the
    test suite can mock around it without forcing cv2 import at module load.
    """
    import cv2
    import numpy as np

    arr = np.frombuffer(photo_bytes, dtype=np.uint8)
    bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if bgr is None:
        raise ValueError("Failed to decode photo bytes as image")
    return bgr


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _stream(
    db: AsyncSession,
    job: IdlaserDraftJob,
    photo_bytes: bytes,
    triggered_by_id: uuid.UUID,
    *,
    manual_corners: list[list[float]] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Core SSE bridge. Sets job RUNNING, drains a thread-pipeline's
    progress callbacks onto an asyncio.Queue, yields each event, and
    finalises the job row (READY / NEEDS_REVIEW / FAILED) on the way out.

    Two paths:
      - manual_corners is None → process_one_streaming (full pipeline)
      - manual_corners is set → reprocess_streaming (skip detect)
    """
    loop = asyncio.get_running_loop()
    q: asyncio.Queue[dict | None] = asyncio.Queue()

    # Mark RUNNING + record started_at before any thread work.
    job.state = IdlaserDraftJobState.RUNNING
    job.started_at = datetime.now(timezone.utc)
    if manual_corners is not None:
        job.manual_corners = manual_corners
    await db.commit()

    yield {
        "type": "job.started",
        "payload": {
            "job_id": str(job.id),
            "photo_attachment_id": (
                str(job.photo_attachment_id)
                if job.photo_attachment_id else None
            ),
        },
        "timestamp": _now_iso(),
        "job_state": job.state.value,
    }

    def progress_cb(stage: str, payload: dict[str, Any]) -> None:
        # Called from worker thread. Must not touch event loop directly.
        event = {
            "type": stage,
            "payload": payload,
            "timestamp": _now_iso(),
        }
        loop.call_soon_threadsafe(q.put_nowait, event)

    template = load_template(settings.IDLASER_TEMPLATE_PATH)

    async def runner() -> None:
        try:
            bgr = _bgr_from_bytes(photo_bytes)
            # IDLASER_TIMEOUT_S enforced here. asyncio.wait_for cancels
            # the awaitable on timeout; the underlying thread is not
            # killed but will finish on its own (bounded CPU pipeline).
            if manual_corners is None:
                result = await asyncio.wait_for(
                    asyncio.to_thread(
                        _run_pipeline_with_retry, bgr, template, progress_cb,
                    ),
                    timeout=settings.IDLASER_TIMEOUT_S,
                )
            else:
                result = await asyncio.wait_for(
                    asyncio.to_thread(
                        _run_reprocess_with_retry,
                        bgr,
                        manual_corners,
                        template,
                        progress_cb,
                    ),
                    timeout=settings.IDLASER_TIMEOUT_S,
                )

            if result.status == "AUTO":
                attachment = await _persist_dxf(
                    db, job, result.dxf_bytes or b"", triggered_by_id,
                )
                job.state = IdlaserDraftJobState.READY
                job.result_attachment_id = attachment.id
                job.completed_at = datetime.now(timezone.utc)
                await db.commit()
                loop.call_soon_threadsafe(
                    q.put_nowait,
                    {
                        "type": "export.completed",
                        "payload": {
                            "result_attachment_id": str(attachment.id),
                        },
                        "timestamp": _now_iso(),
                    },
                )
            else:
                job.state = IdlaserDraftJobState.NEEDS_REVIEW
                job.completed_at = datetime.now(timezone.utc)
                await db.commit()
                loop.call_soon_threadsafe(
                    q.put_nowait,
                    {
                        "type": "review_required",
                        "payload": {
                            "reason": result.review_reason,
                            "best_guess_corners": result.best_guess_corners,
                            "rectified_preview_url": None,
                        },
                        "timestamp": _now_iso(),
                    },
                )
        except asyncio.TimeoutError:
            msg = f"Exceeded {settings.IDLASER_TIMEOUT_S}s"
            job.state = IdlaserDraftJobState.FAILED
            job.error_message = msg
            job.completed_at = datetime.now(timezone.utc)
            await db.commit()
            loop.call_soon_threadsafe(
                q.put_nowait,
                {
                    "type": "error",
                    "payload": {"stage": "pipeline", "message": msg},
                    "timestamp": _now_iso(),
                },
            )
        except Exception as exc:  # noqa: BLE001 — boundary
            logger.exception(
                "Pipeline failure for job %s: %s", job.id, exc,
            )
            job.state = IdlaserDraftJobState.FAILED
            job.error_message = str(exc)
            job.completed_at = datetime.now(timezone.utc)
            await db.commit()
            loop.call_soon_threadsafe(
                q.put_nowait,
                {
                    "type": "error",
                    "payload": {"stage": "pipeline", "message": str(exc)},
                    "timestamp": _now_iso(),
                },
            )
        finally:
            loop.call_soon_threadsafe(q.put_nowait, None)  # sentinel

    # Note: if the client AbortController closes the SSE stream
    # mid-pipeline, runner_task keeps pushing to the queue with no
    # consumer — memory grows by event count until pipeline finishes.
    # Acceptable for v1 (<10 concurrent users); revisit if profiling
    # shows real leak under load.
    runner_task = asyncio.create_task(runner())
    try:
        while True:
            event = await q.get()
            if event is None:
                break
            event["job_state"] = job.state.value
            yield event
    finally:
        if not runner_task.done():
            runner_task.cancel()


async def run_draft_pipeline_sse(
    db: AsyncSession,
    job: IdlaserDraftJob,
    photo_bytes: bytes,
    triggered_by_id: uuid.UUID,
) -> AsyncIterator[dict[str, Any]]:
    """Public: full-pipeline SSE stream (POST /generate-draft)."""
    async for event in _stream(db, job, photo_bytes, triggered_by_id):
        yield event


async def run_reprocess_pipeline_sse(
    db: AsyncSession,
    job: IdlaserDraftJob,
    photo_bytes: bytes,
    triggered_by_id: uuid.UUID,
    corners: list[list[float]],
) -> AsyncIterator[dict[str, Any]]:
    """Public: manual-corners reprocess SSE stream (POST /manual-corners)."""
    async for event in _stream(
        db, job, photo_bytes, triggered_by_id, manual_corners=corners,
    ):
        yield event
