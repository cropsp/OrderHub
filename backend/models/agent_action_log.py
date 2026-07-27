"""
OrderHub CRM — Agent Action Log (MCP-WAREHOUSE §5.8)

Append-only record of every write an AI agent performs through the MCP server.

Why this exists when the domain tables already stamp `user_id`: those tables
record *what changed* (a receipt row, a movement row), never *why*. The agent's
whole job is interpreting an unstructured cost sheet — the mapping decision
("this sheet line means 12 dm² of Italian black leather at 597 UAH") is the part
that exists nowhere afterwards. `tool` + `arguments` capture that intent, and
`object_type`/`object_id` tie it to the row that resulted, which is what makes
"undo what the agent did last Tuesday" an answerable question.

Written by the MCP server itself via POST /api/agent-actions, because the tool
name and arguments are known only at the MCP layer — the backend sees only the
resulting REST call. The MCP process therefore needs no database access of its
own (MCP-WAREHOUSE §5.4).

Failed attempts are recorded too (`ok=false` + `error`): an agent repeatedly
hitting a 403 or a validation error is exactly the pattern an operator wants
visible.

Column shape deliberately mirrors `access_audit` (actor_id, object_type,
object_id, created_at) so the two audit surfaces read the same way.
"""

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base, UUIDPrimaryKeyMixin


class AgentActionLog(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "agent_action_log"

    # The agent user that performed the action. RESTRICT: the log outlives any
    # attempt to delete the principal, same reasoning as the receipt tables.
    actor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    # MCP tool name, e.g. "record_material_receipt".
    tool: Mapped[str] = mapped_column(String(64), nullable=False)
    # The arguments the agent chose — the intent record. JSONB so it stays
    # queryable ("every receipt the agent booked against material X").
    arguments: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    # Did the underlying REST call succeed?
    ok: Mapped[bool] = mapped_column(Boolean, nullable=False)
    # What the agent was acting on: "material" | "material_receipt" |
    # "material_movement" | "overhead_material" | "overhead_receipt" | "bom".
    object_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    # Id of the affected/created row, when there is a single one.
    object_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    # One human-readable line, written by the tool: what actually happened in the
    # owner's terms ("+25 dm² Шкіра @ 597.14 UAH; unit cost 580.00 -> 597.14").
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Populated when ok=false: the API's own `detail`, verbatim.
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    __table_args__ = (
        # "what did the agent do, newest first" — the review query.
        Index("ix_agent_action_log_actor_created", "actor_id", "created_at"),
    )

    def __repr__(self) -> str:
        outcome = "ok" if self.ok else "FAILED"
        return (
            f"<AgentActionLog {self.tool} {outcome} "
            f"{self.object_type}={self.object_id}>"
        )
