"""add Nova Poshta delivery tracking tables (WB-TRACK-1)

Two additive tables, no data backfill, nothing existing is touched:

  * `wb_parcel_tracking` — current state, one row per tracked carrier number.
    Keyed by `tracking_number` rather than `shipment_id` so a parcel re-issued
    under a new NP number keeps its old log.
  * `wb_tracking_event` — one row per observed status transition.

Status columns are raw text (task rule 3): the codes we actually observe
include 80, 115 and 121, none of which appears in any published Nova Poshta
status list, so an enum would be a lie the DB has to enforce.

Reversible: downgrade drops both tables.

Revision ID: c7e1b4d93f28
Revises: b8d3f0a25c47
Create Date: 2026-08-05 21:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "c7e1b4d93f28"
down_revision: Union[str, None] = "b8d3f0a25c47"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "wb_parcel_tracking",
        sa.Column("tracking_number", sa.String(length=32), nullable=False),
        sa.Column("shipment_id", sa.UUID(), nullable=False),
        sa.Column("carrier", sa.String(length=64), nullable=True),
        sa.Column("status_code", sa.String(length=8), nullable=True),
        sa.Column("status_text", sa.Text(), nullable=True),
        sa.Column("np_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("np_last_movement_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "np_scheduled_delivery_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column("np_delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("city_recipient", sa.String(length=255), nullable=True),
        sa.Column(
            "international_delivery_type", sa.String(length=32), nullable=True
        ),
        sa.Column(
            "undelivery_reasons",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("no_data_since", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "first_polled_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_polled_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_change_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("polling_stopped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stopped_reason", sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(
            ["shipment_id"], ["wb_parcel.shipment_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("tracking_number"),
    )
    op.create_index(
        "ix_wb_parcel_tracking_shipment_id",
        "wb_parcel_tracking",
        ["shipment_id"],
    )

    op.create_table(
        "wb_tracking_event",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tracking_number", sa.String(length=32), nullable=False),
        sa.Column("status_code", sa.String(length=8), nullable=True),
        sa.Column("status_text", sa.Text(), nullable=True),
        sa.Column(
            "np_tracking_update_date", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "observed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tracking_number"],
            ["wb_parcel_tracking.tracking_number"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_wb_tracking_event_number_observed",
        "wb_tracking_event",
        ["tracking_number", sa.text("observed_at DESC")],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_wb_tracking_event_number_observed", table_name="wb_tracking_event"
    )
    op.drop_table("wb_tracking_event")
    op.drop_index(
        "ix_wb_parcel_tracking_shipment_id", table_name="wb_parcel_tracking"
    )
    op.drop_table("wb_parcel_tracking")
