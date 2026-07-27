"""OrderHub CRM — Agent Action Log schemas (MCP-WAREHOUSE §5.8)."""

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class AgentActionCreate(BaseModel):
    """One reported agent action. Posted by the MCP server after each write."""

    tool: str = Field(..., max_length=64)
    arguments: dict[str, Any] = Field(default_factory=dict)
    ok: bool
    object_type: Optional[str] = Field(None, max_length=32)
    object_id: Optional[str] = Field(None, max_length=64)
    summary: Optional[str] = None
    error: Optional[str] = None


class AgentActionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    actor_id: uuid.UUID
    actor_email: Optional[str] = None  # joined for readability
    tool: str
    arguments: dict[str, Any]
    ok: bool
    object_type: Optional[str]
    object_id: Optional[str]
    summary: Optional[str]
    error: Optional[str]
    created_at: datetime
