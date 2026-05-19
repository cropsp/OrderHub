"""
OrderHub CRM — IdlaserDraftJob Schemas (S004-mcp-wrapper)

Request/response Pydantic models for the three idlaser routes:
generate-draft (SSE), manual-corners (SSE), status (JSON polling).
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


JobStateLiteral = Literal[
    "pending", "running", "needs_review", "ready", "failed", "cancelled",
]


class IdlaserDraftJobCreate(BaseModel):
    """Body for POST /api/orders/{order_id}/generate-draft."""

    photo_attachment_id: UUID


class ManualCornersRequest(BaseModel):
    """Body for POST /api/orders/{order_id}/draft-jobs/{job_id}/manual-corners.

    `corners` is exactly 4 [x, y] points in original-photo pixel coords.
    """

    corners: list[list[float]] = Field(..., min_length=4, max_length=4)


class IdlaserDraftJobResponse(BaseModel):
    id: UUID
    order_id: UUID
    photo_attachment_id: UUID | None
    result_attachment_id: UUID | None
    triggered_by_id: UUID
    state: JobStateLiteral
    manual_corners: list[list[float]] | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class DraftJobStatusResponse(BaseModel):
    """Polling fallback for clients without SSE; also used in tests."""

    id: UUID
    state: JobStateLiteral
    result_attachment_id: UUID | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None

    class Config:
        from_attributes = True
