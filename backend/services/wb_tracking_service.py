"""
OrderHub CRM — WesternBid Delivery Tracking Service (WB-TRACK-1)

Four jobs, in the order the data flows:

  1. `select_candidates`  — which parcels to poll, and when one stops being polled.
  2. `record_poll`        — turn a batch of NP records into status CHANGES.
  3. `classify_parcels`   — the ONE definition of delivered / moving / problem /
                            no-data / untracked, plus the two attention signals.
  4. `sync_alerts`        — WB-ALERTS-1: turn point 3's output into the handful
                            of alerts worth pushing onto the dashboard.

Point 3 is load-bearing. The MCP tool consumes it today, the `WB-TRACK-2`
monitoring page consumes the same call unchanged, and point 4 reads its output
rather than re-deriving anything; none of the three classifies in its own
response-shaping code. That is how two definitions of "stuck" would otherwise
come to exist and disagree.

Point 4 lives here rather than in a `wb_alert_service` module for one concrete
reason: `run_poll` would import it and it would import `classify_parcels` back,
and a circular import broken by a function-level import is worse than one more
section in a cohesive file.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.app_setting import (
    AppSetting,
    WB_ALERT_NO_DATA_DAYS,
    WB_ALERT_OVERDUE_DAYS,
    WB_ALERT_UNTRACKED_DAYS,
    WB_TRACKING_STALLED_DAYS,
)
from models.order import Order
from models.wb_parcel import WbParcel
from models.wb_parcel_alert import WbParcelAlert
from models.wb_tracking import WbParcelTracking, WbTrackingEvent
from services.np_tracking import (
    NovaPoshtaTrackingClient,
    is_no_data,
    parse_np_datetime,
)

logger = logging.getLogger(__name__)


# ── Status code semantics ──────────────────────────────────────────────────
#
# Codes are RAW TEXT everywhere (task rule 3) and these sets are the only place
# any meaning is attached. Two sources, and the difference matters:
#
#   OBSERVED   — seen in our own data, with the date and count.
#   DOCUMENTED — published by Nova Post's international API portal
#                (api-portal.novapost.com .../shipments/tracking-shipment.md)
#                but never yet seen here.
#
# Nova Poshta's public developer portal 403s every non-browser fetch, and its
# keyless `Common.getDocumentStatuses` directory is a DIFFERENT namespace
# (StateId/GroupId, not StatusCode) — so the portal above is the only citable
# list, and codes we observe can still be absent from it (80 is).

# Terminal success. "9" is the ONLY code OBSERVED in this population (21 of 77
# on 2026-08-05). 10 and 11 are DOCUMENTED variants of the same "closed" state
# that carry a money transfer back to the sender — impossible on an export
# parcel, so they sit here defensively and have never been seen.
DELIVERED_CODES = frozenset({"9", "10", "11"})

# The parcel is not moving on its own and needs a human. ONLY "111" has been
# OBSERVED (1 of 77, Excelsior, 2026-08-05). Every other code here is
# DOCUMENTED and has never occurred in our data — if one shows up, that is new
# information, not a bug.
PROBLEM_CODES = frozenset(
    {
        "2",    # Deleted                          (DOCUMENTED, never observed)
        "99",   # Postomat delivery impossible     (DOCUMENTED, never observed)
        "102",  # Returns — sender ordered         (DOCUMENTED, never observed)
        "103",  # Refusal of shipment              (DOCUMENTED, never observed)
        "104",  # Redirecting                      (DOCUMENTED, never observed)
        "105",  # Utilization                      (DOCUMENTED, never observed)
        "110",  # Transferred to temporary storage (DOCUMENTED, never observed)
        "111",  # Failed delivery attempt          (OBSERVED 2026-08-05)
        "112",  # Delivery date postponed          (DOCUMENTED, never observed)
        "113",  # Storage period expired           (DOCUMENTED, never observed)
        "116",  # Broker refusal                   (DOCUMENTED, never observed)
        "117",  # Cargo lost at customs            (DOCUMENTED, never observed)
        "118",  # Forbidden content                (DOCUMENTED, never observed)
        "123",  # Awaiting info from recipient     (DOCUMENTED, never observed)
    }
)
# Everything else — including any code in neither set, and any code Nova Poshta
# invents tomorrow — is "moving". Unknown NEVER means delivered.

# A code-111 parcel is flagged the moment it appears, because contacting the
# customer is an action rather than an observation. The alternative — flag it
# only once it survives a retry window, since couriers often re-attempt the next
# day — is a real refinement we cannot yet justify: there is exactly one 111 in
# the data and no history of how long they last. The transition log below is
# what will supply that distribution (WB-TRACK-1-followup-1).

# WB's own identifier for the Nova Poshta leg. Verified exhaustive across all 84
# mirrored parcels on 2026-08-05: the only Identifier values in existence are
# "WesternBid" (WB's internal WBX… id, on every parcel), "NovaPost" (77 parcels,
# all `5950…`) and "UPS" (6).
NOVAPOST_IDENTIFIER = "NovaPost"

# Days without a Nova Poshta scan before an undelivered parcel counts as
# stalled. Overridable via app_settings (task rule 4 — configuration, not a
# literal in a condition).
#
# Chosen from the real distribution rather than rounded to taste. Across the 55
# in-flight parcels on 2026-08-05, days since `TrackingUpdateDate` ran p50 0.37,
# p75 0.99, p90 1.17 — healthy parcels get scanned at least daily — and then the
# distribution had a HOLE between 1.61 and 4.29 days before a tail of four
# genuinely stuck ones (4.29, 4.97, 7.04, 7.11). Any threshold in [1.7, 4.2]
# selects exactly those four; 3 sits in the middle of that empty band, so the
# choice is maximally insensitive to where the line falls.
DEFAULT_STALLED_DAYS = 3

# Minimum gap between manual `POST /tracking/refresh` polls (WB-TRACK-2).
# Enforced SERVER-side against the freshness signal itself — see
# `load_last_polled_at` — so a disabled button stays a hint rather than a guard.
# 5 minutes: long enough that a page anyone with the role can open cannot be
# turned into a loop against a third-party endpoint, short enough that a manager
# looking at a 12-day-overdue parcel is never told to come back later.
MANUAL_POLL_COOLDOWN_MINUTES = 5

# A parcel this old stops being polled whatever state it is in, so a parcel
# stuck in March is not re-polled forever. The worst end-to-end transit ever
# observed is 31.3 days (p90 11.4), so 60 is ~2x the worst case.
WB_TRACKING_MAX_AGE_DAYS = 60

# Parcel states. Raw strings rather than an enum, matching the columns they
# summarise, and stable enough for the WB-TRACK-2 page to key its groups off.
STATE_DELIVERED = "delivered"
STATE_MOVING = "moving"
STATE_PROBLEM = "problem"
STATE_NO_DATA = "no_data"
STATE_UNTRACKED = "untracked"

STOPPED_DELIVERED = "delivered"
STOPPED_AGED_OUT = "aged_out"


# ── alerts (WB-ALERTS-1) ───────────────────────────────────────────────────
#
# Four kinds, each mapping to ONE concrete action. They exist because two weeks
# after `/westernbid` shipped, nobody had opened it — a pull surface does not
# get pulled — so the page's findings now come to the operator on the dashboard.
#
# Every condition below reads a field `classify_parcels` already computed.
# Nothing here re-derives "stuck": that would be the second definition this
# whole subsystem is built to avoid.

# Nova Poshta reports a problem code. Keyed off the `problem` STATE rather than
# a literal "111": `classify_parcels` already owns the code→meaning mapping, and
# narrowing to 111 would silently drop the other thirteen PROBLEM_CODES (broker
# refusal, cargo lost at customs, storage period expired) — each of which needs
# a human just as much. Only 111 has ever been OBSERVED. Action: contact the
# customer.
ALERT_DELIVERY_PROBLEM = "delivery_problem"

# Nova Poshta has returned a stub for this parcel for longer than any recovery
# we have ever seen. Action: look it up in the WesternBid cabinet.
ALERT_NO_DATA_STUCK = "no_data_stuck"

# Past Nova Poshta's own delivery promise by a wide margin. Deliberately NOT
# every overdue parcel — 17 of 19 attention rows were overdue on 2026-08-20, and
# an alert that fires on all of them is the ignored surface again.
ALERT_OVERDUE_LONG = "overdue_long"

# A carrier we cannot query at all (UPS / USPS / the cancelled parcel), old
# enough that "still in flight" has stopped being a plausible explanation.
# Action: check the carrier's own number by hand.
ALERT_UNTRACKED_AGING = "untracked_aging"

# Severity, worst first. Used to order the wire payload; NOT a precedence rule —
# several kinds may be open on one parcel at once (task rule 3 dedupes per
# (parcel, kind), not per parcel).
ALERT_KIND_ORDER = (
    ALERT_DELIVERY_PROBLEM,
    ALERT_NO_DATA_STUCK,
    ALERT_OVERDUE_LONG,
    ALERT_UNTRACKED_AGING,
)

# How an alert closed itself. Two values, distinguished on purpose:
#   cleared  — the parcel is still classified and the condition went away.
#   aged_out — the parcel left the WB_TRACKING_MAX_AGE_DAYS window, i.e. we
#              stopped looking. For `untracked_aging` that is the only
#              non-manual exit there can ever be, because WesternBid's status
#              vocabulary is creation-time only and no onward carrier number
#              exists in any source we hold — so calling it "cleared" would
#              claim knowledge we do not have.
RESOLUTION_CLEARED = "cleared"
RESOLUTION_AGED_OUT = "aged_out"

# Days dark before `no_data` becomes actionable. The 2026-08-20 review settled
# this empirically: of 45 parcels that ever went dark, 43 recovered on their
# own, spells lasting 1-5 days (avg 2.15, ceiling 5.0). 6 is one day past the
# observed ceiling, and on the review date it selected exactly one parcel.
DEFAULT_ALERT_NO_DATA_DAYS = 6

# Days past Nova Poshta's scheduled delivery date before an undelivered parcel
# becomes actionable. `is_overdue` alone was 17 of 19 attention rows on
# 2026-08-20; this is the long tail of that, not a mirror of it.
DEFAULT_ALERT_OVERDUE_DAYS = 7

# Days since WB created an UNTRACKABLE parcel before it becomes actionable.
# Worst end-to-end transit ever observed is 31.3 days (p90 11.4), so 14 is
# comfortably inside "should have arrived by now" without being noisy. Expect
# ~6 alerts once at launch from the existing untracked backlog.
DEFAULT_ALERT_UNTRACKED_DAYS = 14


def extract_novapost_number(parcel: WbParcel) -> str | None:
    """Return the Nova Poshta tracking number for a parcel, or None.

    `tracking_numbers` holds objects `{"Identifier": …, "TrackingNumber": …}` and
    a parcel carries two: WB's internal `WBX…` and the carrier's. The `WBX…`
    element is never a carrier number, so selection is by Identifier — verified
    exhaustive and unambiguous: 77 of 77 `NovaPost` elements are `5950…` numbers,
    with no false positives.

    None means the parcel cannot be tracked this sprint: the 6 UPS/USPS parcels,
    plus one canceled NovaPost parcel whose array holds only the `WBX…` element.
    Those are reported as `untracked`, never silently dropped (task rule 7).
    """
    for element in parcel.tracking_numbers or []:
        if not isinstance(element, dict):
            continue
        if element.get("Identifier") == NOVAPOST_IDENTIFIER:
            number = (element.get("TrackingNumber") or "").strip()
            if number:
                return number
    return None


def carrier_tracking_numbers(parcel: WbParcel) -> list[dict]:
    """Every well-formed `{Identifier, TrackingNumber}` element, verbatim (WB-TRACK-2).

    The complement of `extract_novapost_number`, and deliberately NOT a second
    selection rule: it filters only on shape, never on Identifier. The UPS and
    ConsolidationOptimum numbers it returns are the ONLY thing an operator can
    act on for the 7 `untracked` parcels, which by definition have no Nova
    Poshta number to show.

    Defensive for the same reason as its sibling: `tracking_numbers` is JSONB
    mirrored from WB, and bare strings have been seen in it.
    """
    numbers: list[dict] = []
    for element in parcel.tracking_numbers or []:
        if not isinstance(element, dict):
            continue
        number = (element.get("TrackingNumber") or "").strip()
        if not number:
            continue
        identifier = (element.get("Identifier") or "").strip() or None
        numbers.append({"Identifier": identifier, "TrackingNumber": number})
    return numbers


def _coerce_days(raw: object | None, key: str, default: int) -> int:
    """One app_settings day-threshold, coerced or loudly defaulted.

    Extracted from `load_stalled_days` when WB-ALERTS-1 added three more
    thresholds; the behaviour is byte-for-byte what that function did, and its
    existing tests are the proof. A bad value never raises and never silently
    becomes something surprising — it logs and falls back, because a threshold
    that quietly reads 0 would flag every parcel in the system.
    """
    if raw is None:
        return default
    try:
        value = int(Decimal(str(raw)))
    except (InvalidOperation, ValueError):
        logger.warning(
            "Unparseable %s=%r — falling back to %d days", key, raw, default
        )
        return default
    if value < 1:
        logger.warning("%s=%r is below 1 day — falling back to %d", key, raw, default)
        return default
    return value


async def load_stalled_days(db: AsyncSession) -> int:
    """Read the stalled threshold from app_settings, falling back to the default.

    Exactly ONE `db.execute`, and it must stay that way: `classify_parcels`
    calls this first and the classification tests drive it with an ordered
    `AsyncMock(side_effect=[...])`.
    """
    raw = (
        await db.execute(
            select(AppSetting.value).where(
                AppSetting.key == WB_TRACKING_STALLED_DAYS
            )
        )
    ).scalar_one_or_none()
    return _coerce_days(raw, WB_TRACKING_STALLED_DAYS, DEFAULT_STALLED_DAYS)


@dataclass
class Candidate:
    """One parcel to poll, with its existing tracking row if it has one."""

    parcel: WbParcel
    tracking_number: str
    tracking: WbParcelTracking | None


async def select_candidates(db: AsyncSession, now: datetime | None = None) -> list[Candidate]:
    """Parcels to poll on this run, retiring the ones that have aged out.

    A parcel ENTERS the set when it has a Nova Poshta number, and LEAVES it in
    exactly two ways: delivered (stamped by `record_poll`, since a delivered
    parcel cannot un-deliver), or older than `WB_TRACKING_MAX_AGE_DAYS`, stamped
    here and logged so an indefinitely-stuck parcel is retired loudly.

    `problem`-state parcels keep being polled: a return is still moving, and its
    terminal state matters.

    Selection happens in Python rather than in a JSONB predicate: the candidate
    population is a few hundred rows at most, and keeping the rule in
    `extract_novapost_number` means the tests exercise the same code the poller
    does.
    """
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=WB_TRACKING_MAX_AGE_DAYS)

    parcels = (await db.execute(select(WbParcel))).scalars().all()
    tracking_rows = {
        row.tracking_number: row
        for row in (await db.execute(select(WbParcelTracking))).scalars().all()
    }

    candidates: list[Candidate] = []
    retired = 0
    for parcel in parcels:
        number = extract_novapost_number(parcel)
        if number is None:
            continue

        tracking = tracking_rows.get(number)
        if tracking is not None and tracking.polling_stopped_at is not None:
            continue

        # `wb_created_at` is nullable in the mirror; treat an unknown creation
        # date as young rather than retiring a parcel we know nothing about.
        if parcel.wb_created_at is not None and parcel.wb_created_at < cutoff:
            if tracking is not None:
                tracking.polling_stopped_at = now
                tracking.stopped_reason = STOPPED_AGED_OUT
                retired += 1
            continue

        candidates.append(
            Candidate(parcel=parcel, tracking_number=number, tracking=tracking)
        )

    if retired:
        logger.info(
            "WB tracking: retired %d parcel(s) after %d days without reaching a "
            "terminal status — they will not be polled again",
            retired,
            WB_TRACKING_MAX_AGE_DAYS,
        )
    return candidates


async def record_poll(
    db: AsyncSession,
    candidates: list[Candidate],
    records: list[dict],
    now: datetime | None = None,
) -> dict[str, int]:
    """Fold a batch of NP records into the tracking tables.

    Writes a `WbTrackingEvent` only on an observed CHANGE (task rule 2):
    re-polling an unchanged parcel adds no row. `status_text` participates in the
    comparison on purpose — the text carries the destination city ("Відправлення
    прямує до Phoenix"), so a same-code city change is a real movement.
    """
    now = now or datetime.now(timezone.utc)
    by_number = {c.tracking_number: c for c in candidates}
    by_record = {
        str(r.get("Number") or "").strip(): r for r in records if r.get("Number")
    }

    summary = {
        "polled": 0,
        "created": 0,
        "changed": 0,
        "delivered": 0,
        "no_data": 0,
        "missing": 0,
    }

    for number, candidate in by_number.items():
        record = by_record.get(number)
        if record is None:
            # NP did not return this document at all — distinct from returning a
            # stub for it. Leave the row untouched; the next run retries.
            summary["missing"] += 1
            logger.warning("WB tracking: no NP record returned for %s", number)
            continue

        summary["polled"] += 1
        tracking = candidate.tracking
        if tracking is None:
            tracking = WbParcelTracking(
                tracking_number=number,
                shipment_id=candidate.parcel.shipment_id,
                carrier=candidate.parcel.shipping_type,
                first_polled_at=now,
                last_polled_at=now,
            )
            db.add(tracking)
            candidate.tracking = tracking
            summary["created"] += 1

        tracking.last_polled_at = now

        if is_no_data(record):
            # Keep the last RESOLVED status and its dates — losing them would
            # throw away the only information we have about where the parcel got
            # to. Flag it separately and keep polling: it may come back.
            if tracking.no_data_since is None:
                tracking.no_data_since = now
                tracking.last_change_at = now
                db.add(
                    WbTrackingEvent(
                        tracking_number=number,
                        status_code=str(record.get("StatusCode") or "") or None,
                        status_text=None,
                        observed_at=now,
                    )
                )
                summary["changed"] += 1
                logger.info(
                    "WB tracking: Nova Poshta returned no data for %s "
                    "(StatusCode %r); keeping last known status %r",
                    number,
                    record.get("StatusCode"),
                    tracking.status_text,
                )
            summary["no_data"] += 1
            continue

        # Resolved again (or for the first time).
        tracking.no_data_since = None

        status_code = str(record.get("StatusCode") or "") or None
        status_text = (record.get("Status") or "").strip() or None
        movement_at = parse_np_datetime(record.get("TrackingUpdateDate"))

        if (status_code, status_text) != (tracking.status_code, tracking.status_text):
            db.add(
                WbTrackingEvent(
                    tracking_number=number,
                    status_code=status_code,
                    status_text=status_text,
                    np_tracking_update_date=movement_at,
                    observed_at=now,
                )
            )
            tracking.last_change_at = now
            summary["changed"] += 1

        tracking.status_code = status_code
        tracking.status_text = status_text
        tracking.np_created_at = parse_np_datetime(record.get("DateCreated"))
        tracking.np_last_movement_at = movement_at
        tracking.np_scheduled_delivery_at = parse_np_datetime(
            record.get("ScheduledDeliveryDate")
        )
        tracking.city_recipient = (record.get("CityRecipient") or "").strip() or None
        tracking.international_delivery_type = (
            record.get("InternationalDeliveryType") or ""
        ).strip() or None
        # Stored, never read by any logic — see the model docstring.
        raw_reasons = record.get("UndeliveryReasons")
        tracking.undelivery_reasons = raw_reasons if raw_reasons else None

        if status_code in DELIVERED_CODES:
            # `RecipientDateTime`, not `ActualDeliveryDate`: the latter is empty
            # on every keyless response we have ever seen.
            tracking.np_delivered_at = parse_np_datetime(
                record.get("RecipientDateTime")
            ) or movement_at
            tracking.polling_stopped_at = now
            tracking.stopped_reason = STOPPED_DELIVERED
            summary["delivered"] += 1

    return summary


async def load_last_polled_at(db: AsyncSession) -> datetime | None:
    """When the poller last successfully touched any parcel (WB-TRACK-2).

    The same value `classify_parcels` reports as `polled_at`, read on its own so
    the refresh route can check the cooldown without classifying 84 parcels
    first. None means the job has never run — which is never a cooldown.
    """
    return (
        await db.execute(select(func.max(WbParcelTracking.last_polled_at)))
    ).scalar_one()


async def run_poll(db: AsyncSession) -> dict[str, int]:
    """Select, fetch, record one full tracking poll, then sync alerts (WB-TRACK-2).

    THE poll. The daily scheduler job and the manual refresh route both call
    this and neither reimplements it — the same rule `classify_parcels` follows
    for the classification, applied to the write path: one definition, two
    callers, no parallel path that can drift. WB-ALERTS-1 rides the same pass
    rather than adding a fifth scheduler job, which is what makes a manual
    "Refresh now" update the dashboard alerts too.

    Does NOT commit. Each caller owns its transaction boundary — the scheduler
    commits explicitly, the route lets `get_db` commit — and the aged-out
    retirements written by `select_candidates` need committing even when there
    is nothing left to poll, which is why the empty case still returns normally.

    `sync_alerts` runs on BOTH branches. Untracked parcels are never candidates,
    so the zero-candidate branch is exactly when an `untracked_aging` alert
    would otherwise never be raised — and auto-resolve has to run whether or not
    anything was polled.

    Alert sync is deliberately NOT wrapped in try/except. A failure aborts the
    whole poll, and that is the cheaper mistake: `record_poll` is re-derivable
    (tomorrow's poll refetches from NP and writes the change event then), so an
    aborted run costs freshness rather than data — whereas swallowing would let
    alert generation die in silence, which is the exact failure this sprint
    exists to fix.
    """
    candidates = await select_candidates(db)
    if not candidates:
        summary = {
            "polled": 0,
            "created": 0,
            "changed": 0,
            "delivered": 0,
            "no_data": 0,
            "missing": 0,
        }
    else:
        client = NovaPoshtaTrackingClient()
        records = await client.get_status_documents(
            [c.tracking_number for c in candidates]
        )
        summary = await record_poll(db, candidates, records)

    summary.update(await sync_alerts(db))
    return summary


@dataclass
class ClassifiedParcel:
    """One parcel as both consumers need it.

    The MCP tool renders a subset as text; `WB-TRACK-2` renders the whole record
    as a table row. Every field the page needs is carried NOW so the page is a
    new reader rather than a migration.
    """

    tracking_number: str | None
    carrier: str | None
    shipment_id: UUID
    order_id: UUID | None
    order_number: str | None
    # Every carrier number WB reported. `tracking_number` above is the Nova
    # Poshta one and is None for `untracked`; this is what the page shows there.
    tracking_numbers: list[dict]

    state: str
    status_code: str | None
    status_text: str | None

    is_overdue: bool
    is_stalled: bool
    days_overdue: float | None
    days_since_movement: float | None

    recipient_name: str | None
    city_recipient: str | None
    recipient_country_code: str | None

    scheduled_delivery_at: datetime | None
    last_movement_at: datetime | None
    delivered_at: datetime | None
    no_data_since: datetime | None

    wb_status: str | None
    payment_status: str | None
    wb_created_at: datetime | None


@dataclass
class TrackingOverview:
    counts: dict[str, int] = field(default_factory=dict)
    parcels: list[ClassifiedParcel] = field(default_factory=list)
    polled_at: datetime | None = None
    stalled_days: int = DEFAULT_STALLED_DAYS


def _days_between(later: datetime, earlier: datetime | None) -> float | None:
    if earlier is None:
        return None
    return round((later - earlier).total_seconds() / 86400, 2)


async def classify_parcels(
    db: AsyncSession, now: datetime | None = None
) -> TrackingOverview:
    """The single, server-side attention classification (task rule 7).

    Covers every parcel inside the tracking window, including the ones we cannot
    track: UPS (`1Z…`) and USPS/ConsolidationOptimum (`9261…`) get an explicit
    `untracked` state rather than being omitted. A monitor that silently drops
    ~8% of parcels is worse than one that names them and says "check by hand".
    (The single canceled NovaPost parcel also lands here — not because its WB
    status is read, which would re-introduce exactly the string comparison WB-1
    forbids, but because WB issued it no carrier number.)

    Two independent attention signals, both computed here and nowhere else:
      * overdue — Nova Poshta's OWN `ScheduledDeliveryDate` is in the past and
        the parcel is not delivered. Their commitment, not our guess.
      * stalled — no scan for `stalled_days`, catching a parcel sitting inside a
        generous scheduled window.
    """
    now = now or datetime.now(timezone.utc)
    stalled_days = await load_stalled_days(db)
    cutoff = now - timedelta(days=WB_TRACKING_MAX_AGE_DAYS)

    parcels = (
        (await db.execute(select(WbParcel).order_by(WbParcel.first_seen_at.desc())))
        .scalars()
        .all()
    )
    tracking_rows = {
        row.tracking_number: row
        for row in (await db.execute(select(WbParcelTracking))).scalars().all()
    }

    # `order_id` is populated only when a label was fetched through OrderHub, so
    # it is NULL for most parcels until WB-2. Resolve the few that have one.
    # Two columns, not entities: `Order` eager-loads items, history, attachments,
    # refunds, shop and customer, and a monitor has no use for any of it.
    linked_order_ids = [p.order_id for p in parcels if p.order_id is not None]
    order_numbers: dict[UUID, str | None] = {}
    if linked_order_ids:
        rows = await db.execute(
            select(Order.id, Order.order_number).where(Order.id.in_(linked_order_ids))
        )
        order_numbers = {row.id: row.order_number for row in rows}

    classified: list[ClassifiedParcel] = []
    for parcel in parcels:
        if parcel.wb_created_at is not None and parcel.wb_created_at < cutoff:
            continue

        number = extract_novapost_number(parcel)
        tracking = tracking_rows.get(number) if number else None

        if number is None:
            state = STATE_UNTRACKED
        elif tracking is None:
            # Has a number but has not been polled yet (first run pending).
            state = STATE_MOVING
        elif tracking.status_code in DELIVERED_CODES:
            state = STATE_DELIVERED
        elif tracking.no_data_since is not None:
            state = STATE_NO_DATA
        elif tracking.status_code in PROBLEM_CODES:
            state = STATE_PROBLEM
        else:
            state = STATE_MOVING

        delivered = state == STATE_DELIVERED
        scheduled_at = tracking.np_scheduled_delivery_at if tracking else None
        movement_at = tracking.np_last_movement_at if tracking else None

        days_overdue = None
        if not delivered and scheduled_at is not None and scheduled_at < now:
            days_overdue = _days_between(now, scheduled_at)
        days_since_movement = (
            None if delivered else _days_between(now, movement_at)
        )

        classified.append(
            ClassifiedParcel(
                tracking_number=number,
                carrier=parcel.shipping_type,
                shipment_id=parcel.shipment_id,
                order_id=parcel.order_id,
                order_number=order_numbers.get(parcel.order_id),
                tracking_numbers=carrier_tracking_numbers(parcel),
                state=state,
                status_code=tracking.status_code if tracking else None,
                status_text=tracking.status_text if tracking else None,
                is_overdue=days_overdue is not None,
                is_stalled=(
                    days_since_movement is not None
                    and days_since_movement >= stalled_days
                ),
                days_overdue=days_overdue,
                days_since_movement=days_since_movement,
                recipient_name=parcel.recipient_name,
                city_recipient=tracking.city_recipient if tracking else None,
                recipient_country_code=parcel.recipient_country_code,
                scheduled_delivery_at=scheduled_at,
                last_movement_at=movement_at,
                delivered_at=tracking.np_delivered_at if tracking else None,
                no_data_since=tracking.no_data_since if tracking else None,
                wb_status=parcel.wb_status,
                payment_status=parcel.payment_status,
                wb_created_at=parcel.wb_created_at,
            )
        )

    # Newest first, parcels with no WB creation date last — sorted here rather
    # than in SQL because `wb_created_at` is nullable and the window filter above
    # already walks the list.
    oldest = datetime.min.replace(tzinfo=timezone.utc)
    classified.sort(key=lambda p: p.wb_created_at or oldest, reverse=True)

    counts = {
        "total": len(classified),
        STATE_DELIVERED: sum(1 for p in classified if p.state == STATE_DELIVERED),
        STATE_MOVING: sum(1 for p in classified if p.state == STATE_MOVING),
        STATE_PROBLEM: sum(1 for p in classified if p.state == STATE_PROBLEM),
        STATE_NO_DATA: sum(1 for p in classified if p.state == STATE_NO_DATA),
        STATE_UNTRACKED: sum(1 for p in classified if p.state == STATE_UNTRACKED),
        "overdue": sum(1 for p in classified if p.is_overdue),
        "stalled": sum(1 for p in classified if p.is_stalled),
    }

    polled_at = max(
        (row.last_polled_at for row in tracking_rows.values()), default=None
    )

    return TrackingOverview(
        counts=counts,
        parcels=classified,
        polled_at=polled_at,
        stalled_days=stalled_days,
    )


# ── WB-ALERTS-1: from classification to the dashboard ──────────────────────


@dataclass(frozen=True)
class AlertThresholds:
    """The three configurable ages, resolved once per sync."""

    no_data_days: int = DEFAULT_ALERT_NO_DATA_DAYS
    overdue_days: int = DEFAULT_ALERT_OVERDUE_DAYS
    untracked_days: int = DEFAULT_ALERT_UNTRACKED_DAYS


@dataclass(frozen=True)
class AlertCondition:
    """One (parcel, kind) condition observed to hold RIGHT NOW.

    Not an alert — an observation. `sync_alerts` decides whether it opens a new
    row, refreshes an existing one, or does nothing because the operator already
    dismissed it.
    """

    shipment_id: UUID
    kind: str
    detail: str


async def load_alert_thresholds(db: AsyncSession) -> AlertThresholds:
    """Read all three alert thresholds in ONE query, defaulting per key."""
    rows = await db.execute(
        select(AppSetting.key, AppSetting.value).where(
            AppSetting.key.in_(
                (
                    WB_ALERT_NO_DATA_DAYS,
                    WB_ALERT_OVERDUE_DAYS,
                    WB_ALERT_UNTRACKED_DAYS,
                )
            )
        )
    )
    raw = {row.key: row.value for row in rows}
    return AlertThresholds(
        no_data_days=_coerce_days(
            raw.get(WB_ALERT_NO_DATA_DAYS),
            WB_ALERT_NO_DATA_DAYS,
            DEFAULT_ALERT_NO_DATA_DAYS,
        ),
        overdue_days=_coerce_days(
            raw.get(WB_ALERT_OVERDUE_DAYS),
            WB_ALERT_OVERDUE_DAYS,
            DEFAULT_ALERT_OVERDUE_DAYS,
        ),
        untracked_days=_coerce_days(
            raw.get(WB_ALERT_UNTRACKED_DAYS),
            WB_ALERT_UNTRACKED_DAYS,
            DEFAULT_ALERT_UNTRACKED_DAYS,
        ),
    )


def alert_age_days(now: datetime, raised_at: datetime) -> float:
    """How long an alert has been waiting, in days.

    Public because the router needs it and `_days_between` is internal. Never
    None: `raised_at` is NOT NULL, and a monitoring number that can be None is
    a number every caller has to defend against.
    """
    return _days_between(now, raised_at) or 0.0


def _format_days(days: float) -> str:
    """`9.7` → "9.7", `14.0` → "14". Ukrainian UI, one decimal at most."""
    return f"{days:.0f}" if float(days).is_integer() else f"{days:.1f}"


def detect_alert_conditions(
    parcels: list[ClassifiedParcel],
    thresholds: AlertThresholds,
    now: datetime,
) -> list[AlertCondition]:
    """Which alert conditions hold, given a classification (task rule 7).

    PURE — no session, no I/O, no clock of its own. Every predicate reads a
    field `classify_parcels` already produced; there is no second definition of
    delivered / problem / dark / untracked anywhere in this function.

    A parcel may satisfy several kinds at once and that is intended: task rule 3
    dedupes per (parcel, kind), not per parcel. `59500007135457` on 2026-08-20
    was both dark 9.7 days and long overdue, and those are two different things
    to do about it.

    One consequence worth naming rather than special-casing: `classify_parcels`
    ranks `no_data` ABOVE `problem`, so a code-111 parcel that then goes dark is
    `no_data` and raises `no_data_stuck`, not `delivery_problem`. That is the
    single definition doing its job.
    """
    conditions: list[AlertCondition] = []

    for parcel in parcels:
        # A delivered parcel raises nothing, ever. `days_overdue` is already
        # None for it, but stating the rule beats relying on that.
        if parcel.state == STATE_DELIVERED:
            continue

        if parcel.state == STATE_PROBLEM:
            conditions.append(
                AlertCondition(
                    shipment_id=parcel.shipment_id,
                    kind=ALERT_DELIVERY_PROBLEM,
                    detail=f"Проблема доставки — код {parcel.status_code or '?'}",
                )
            )

        if parcel.state == STATE_NO_DATA:
            dark_days = _days_between(now, parcel.no_data_since)
            if dark_days is not None and dark_days > thresholds.no_data_days:
                conditions.append(
                    AlertCondition(
                        shipment_id=parcel.shipment_id,
                        kind=ALERT_NO_DATA_STUCK,
                        detail=f"Без даних {_format_days(dark_days)} дн.",
                    )
                )

        if (
            parcel.days_overdue is not None
            and parcel.days_overdue > thresholds.overdue_days
        ):
            conditions.append(
                AlertCondition(
                    shipment_id=parcel.shipment_id,
                    kind=ALERT_OVERDUE_LONG,
                    detail=f"Прострочено {_format_days(parcel.days_overdue)} дн.",
                )
            )

        if parcel.state == STATE_UNTRACKED:
            # Needs an age, and `wb_created_at` is nullable in the mirror. No
            # date means no alert rather than a guessed one.
            age_days = _days_between(now, parcel.wb_created_at)
            if age_days is not None and age_days > thresholds.untracked_days:
                carrier = parcel.carrier or "Невідомий перевізник"
                conditions.append(
                    AlertCondition(
                        shipment_id=parcel.shipment_id,
                        kind=ALERT_UNTRACKED_AGING,
                        detail=(
                            f"{carrier} — не відстежується, "
                            f"{_format_days(age_days)} дн."
                        ),
                    )
                )

    return conditions


async def sync_alerts(db: AsyncSession, now: datetime | None = None) -> dict[str, int]:
    """Reconcile the open alert set against what is true right now (WB-ALERTS-1).

    Runs inside `run_poll`, so it inherits the caller's transaction: it only
    `db.add`s and mutates loaded rows, and never commits or flushes.

    Three outcomes per (parcel, kind):

      * condition holds and a row is open  → touch `last_seen_at`, refresh the
        detail text. Nothing is re-raised, which is task rule 3.
      * condition holds and no row is open → open one. If the previous episode
        was dismissed it is already RESOLVED (a dismissal alone never resolves),
        so this only happens after the condition genuinely cleared and came
        back — a new episode, task rule 5.
      * row is open and the condition does not hold → close it. This is the
        load-bearing half: without auto-resolve the dashboard silts up with
        stale alerts and becomes the next surface nobody opens.

    A dismissed row is still OPEN, so it is *touched* rather than re-raised
    while its condition persists — that is what "dismissals don't resurrect"
    means mechanically.
    """
    now = now or datetime.now(timezone.utc)

    overview = await classify_parcels(db, now=now)
    thresholds = await load_alert_thresholds(db)

    conditions = {
        (c.shipment_id, c.kind): c
        for c in detect_alert_conditions(overview.parcels, thresholds, now)
    }
    # Parcels still inside the 60-day window. Used only to tell the two
    # auto-resolutions apart — see RESOLUTION_AGED_OUT.
    in_window = {p.shipment_id for p in overview.parcels}

    open_rows = (
        (
            await db.execute(
                select(WbParcelAlert).where(WbParcelAlert.resolved_at.is_(None))
            )
        )
        .scalars()
        .all()
    )

    opened = 0
    resolved = 0

    for row in open_rows:
        condition = conditions.pop((row.shipment_id, row.kind), None)
        if condition is not None:
            row.last_seen_at = now
            if row.detail != condition.detail:
                row.detail = condition.detail
            continue

        row.resolved_at = now
        row.resolution = (
            RESOLUTION_CLEARED
            if row.shipment_id in in_window
            else RESOLUTION_AGED_OUT
        )
        resolved += 1

    # Whatever the loop above did not claim is new.
    for condition in conditions.values():
        db.add(
            WbParcelAlert(
                shipment_id=condition.shipment_id,
                kind=condition.kind,
                detail=condition.detail,
                raised_at=now,
                last_seen_at=now,
            )
        )
        opened += 1

    if opened or resolved:
        logger.info(
            "WB alerts synced: opened=%d resolved=%d open_now=%d",
            opened,
            resolved,
            len(open_rows) - resolved + opened,
        )

    return {"alerts_opened": opened, "alerts_resolved": resolved}
