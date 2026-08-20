"""WB-ALERTS-1 — dashboard parcel alerts: detection, reconciliation, endpoints.

Mock-based like the rest of the repo — `MagicMock` sessions, real un-persisted
ORM objects, no conftest, no freezegun.

The split the tests lean on is deliberate: `detect_alert_conditions` is a PURE
function over `ClassifiedParcel`s, so every threshold and precedence case is
tested with no session at all. `sync_alerts` is then tested against a patched
`classify_parcels`, which is what isolates "did we reconcile the open set
correctly" from "did we classify correctly" — the latter already has 62 tests
next door in test_wb_tracking.py.

The numbers in the boundary cases are not round figures picked for tidiness.
6 days dark comes from the 2026-08-20 review: 45 parcels ever went dark, 43
recovered, spells lasting 1-5 days with a ceiling of 5.0 — so 5.0d must raise
nothing and 6.1d must raise.
"""
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from models.app_setting import (
    WB_ALERT_NO_DATA_DAYS,
    WB_ALERT_OVERDUE_DAYS,
    WB_ALERT_UNTRACKED_DAYS,
)
from models.user import UserRole
from models.wb_parcel import WbParcel
from models.wb_parcel_alert import WbParcelAlert
from routers.dependencies import require_role
from routers.westernbid import dismiss_parcel_alert, list_parcel_alerts
from services import wb_tracking_service
from services.wb_tracking_service import (
    ALERT_DELIVERY_PROBLEM,
    ALERT_KIND_ORDER,
    ALERT_NO_DATA_STUCK,
    ALERT_OVERDUE_LONG,
    ALERT_UNTRACKED_AGING,
    DEFAULT_ALERT_NO_DATA_DAYS,
    DEFAULT_ALERT_OVERDUE_DAYS,
    DEFAULT_ALERT_UNTRACKED_DAYS,
    RESOLUTION_AGED_OUT,
    RESOLUTION_CLEARED,
    STATE_DELIVERED,
    STATE_MOVING,
    STATE_NO_DATA,
    STATE_PROBLEM,
    STATE_UNTRACKED,
    AlertThresholds,
    ClassifiedParcel,
    TrackingOverview,
    detect_alert_conditions,
    load_alert_thresholds,
    sync_alerts,
)

UTC = timezone.utc
NOW = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)
THRESHOLDS = AlertThresholds()


# ── fixtures ───────────────────────────────────────────────────────────────


def _scalars(items):
    r = MagicMock()
    r.scalars.return_value.all.return_value = list(items)
    return r


def _rows(items):
    """A result iterated directly — key/value column selects."""
    return list(items)


def _db(execute_results=()):
    db = MagicMock()
    db.execute = AsyncMock(side_effect=list(execute_results))
    db.add = MagicMock()
    return db


def _setting(key, value):
    row = MagicMock()
    row.key = key
    row.value = value
    return row


def _classified(**kwargs) -> ClassifiedParcel:
    """A moving, healthy parcel — override one field per test."""
    defaults = dict(
        tracking_number="59500007147707",
        carrier="NovaPost",
        shipment_id=uuid.uuid4(),
        order_id=None,
        order_number=None,
        tracking_numbers=[
            {"Identifier": "NovaPost", "TrackingNumber": "59500007147707"}
        ],
        state=STATE_MOVING,
        status_code="5",
        status_text="Відправлення прямує до  Phoenix.",
        is_overdue=False,
        is_stalled=False,
        days_overdue=None,
        days_since_movement=0.4,
        recipient_name="Jane Doe",
        city_recipient="Phoenix",
        recipient_country_code="US",
        scheduled_delivery_at=None,
        last_movement_at=NOW - timedelta(hours=9),
        delivered_at=None,
        no_data_since=None,
        wb_status="Parcel created",
        payment_status="Paid",
        wb_created_at=NOW - timedelta(days=3),
    )
    defaults.update(kwargs)
    return ClassifiedParcel(**defaults)


def _alert(**kwargs) -> WbParcelAlert:
    defaults = dict(
        id=uuid.uuid4(),
        shipment_id=uuid.uuid4(),
        kind=ALERT_OVERDUE_LONG,
        detail="Прострочено 9 дн.",
        raised_at=NOW - timedelta(days=2),
        last_seen_at=NOW - timedelta(days=1),
    )
    defaults.update(kwargs)
    return WbParcelAlert(**defaults)


def _detect(parcels, thresholds=THRESHOLDS, now=NOW):
    return detect_alert_conditions(parcels, thresholds, now)


def _kinds(conditions):
    return sorted(c.kind for c in conditions)


# ── detection: delivery_problem ────────────────────────────────────────────


def test_the_one_failure_code_we_have_ever_seen_raises_immediately():
    """Code 111, the WB-TRACK-1 asymmetry rule: a false alarm costs one glance,
    a missed failed delivery costs the parcel when it returns to sender."""
    parcel = _classified(state=STATE_PROBLEM, status_code="111")

    (condition,) = _detect([parcel])

    assert condition.kind == ALERT_DELIVERY_PROBLEM
    assert condition.shipment_id == parcel.shipment_id
    assert "111" in condition.detail


def test_every_problem_code_raises_not_only_the_observed_one():
    """The alert keys off the `problem` STATE, so the thirteen DOCUMENTED codes
    reach the operator too. Narrowing to a literal "111" would have made them
    invisible on the one surface anybody looks at."""
    for code in ("103", "113", "117", "123"):
        parcel = _classified(state=STATE_PROBLEM, status_code=code)
        (condition,) = _detect([parcel])
        assert condition.kind == ALERT_DELIVERY_PROBLEM
        assert code in condition.detail


def test_a_problem_parcel_with_no_code_still_raises_readably():
    parcel = _classified(state=STATE_PROBLEM, status_code=None)

    (condition,) = _detect([parcel])

    assert condition.kind == ALERT_DELIVERY_PROBLEM
    assert "?" in condition.detail


# ── detection: no_data_stuck ───────────────────────────────────────────────


def test_a_parcel_dark_inside_the_observed_recovery_window_raises_nothing():
    """5.0 days is the longest recovery ever observed (43 of 45 dark parcels
    came back on their own). Alerting inside that window is alerting on normal."""
    parcel = _classified(
        state=STATE_NO_DATA, no_data_since=NOW - timedelta(days=5.0)
    )

    assert _detect([parcel]) == []


def test_a_parcel_dark_past_the_recovery_ceiling_raises():
    parcel = _classified(
        state=STATE_NO_DATA, no_data_since=NOW - timedelta(days=6.1)
    )

    (condition,) = _detect([parcel])

    assert condition.kind == ALERT_NO_DATA_STUCK
    assert "6.1" in condition.detail


def test_the_no_data_threshold_is_exclusive():
    """Exactly 6.0 days is not "older than 6 days"."""
    parcel = _classified(
        state=STATE_NO_DATA, no_data_since=NOW - timedelta(days=6.0)
    )

    assert _detect([parcel]) == []


def test_a_dark_problem_parcel_raises_the_dark_alert_not_the_problem_one():
    """`classify_parcels` ranks no_data ABOVE problem, and the generator obeys
    that rather than second-guessing it — one definition, task rule 7."""
    parcel = _classified(
        state=STATE_NO_DATA,
        status_code="111",
        no_data_since=NOW - timedelta(days=9.7),
    )

    assert _kinds(_detect([parcel])) == [ALERT_NO_DATA_STUCK]


# ── detection: overdue_long ────────────────────────────────────────────────


def test_a_freshly_overdue_parcel_raises_nothing():
    """17 of 19 attention rows were overdue on 2026-08-20. Mirroring
    `is_overdue` would reproduce the list nobody acts on."""
    parcel = _classified(is_overdue=True, days_overdue=2.4)

    assert _detect([parcel]) == []


def test_a_parcel_overdue_past_the_long_tail_threshold_raises():
    parcel = _classified(is_overdue=True, days_overdue=12.68)

    (condition,) = _detect([parcel])

    assert condition.kind == ALERT_OVERDUE_LONG
    assert "12.7" in condition.detail


def test_the_overdue_threshold_is_exclusive():
    parcel = _classified(is_overdue=True, days_overdue=7.0)

    assert _detect([parcel]) == []


# ── detection: untracked_aging ─────────────────────────────────────────────


def test_a_recent_untracked_parcel_raises_nothing():
    parcel = _classified(
        state=STATE_UNTRACKED,
        tracking_number=None,
        carrier="UPS",
        wb_created_at=NOW - timedelta(days=13),
    )

    assert _detect([parcel]) == []


def test_an_aging_untracked_parcel_raises_and_names_its_carrier():
    parcel = _classified(
        state=STATE_UNTRACKED,
        tracking_number=None,
        carrier="UPS",
        wb_created_at=NOW - timedelta(days=21),
    )

    (condition,) = _detect([parcel])

    assert condition.kind == ALERT_UNTRACKED_AGING
    assert "UPS" in condition.detail
    assert "21" in condition.detail


def test_an_untracked_parcel_with_no_creation_date_raises_nothing():
    """`wb_created_at` is nullable in the mirror. No date means no age, and a
    guessed age is exactly the kind of invention this subsystem refuses."""
    parcel = _classified(
        state=STATE_UNTRACKED, tracking_number=None, wb_created_at=None
    )

    assert _detect([parcel]) == []


def test_an_untracked_parcel_with_no_carrier_still_reads_sensibly():
    parcel = _classified(
        state=STATE_UNTRACKED,
        tracking_number=None,
        carrier=None,
        wb_created_at=NOW - timedelta(days=30),
    )

    (condition,) = _detect([parcel])

    assert "Невідомий перевізник" in condition.detail


# ── detection: cross-cutting ───────────────────────────────────────────────


def test_a_delivered_parcel_never_raises_whatever_else_is_true():
    parcel = _classified(
        state=STATE_DELIVERED,
        status_code="9",
        delivered_at=NOW - timedelta(days=1),
        # Stale signals that would each raise on a live parcel.
        no_data_since=NOW - timedelta(days=40),
        days_overdue=30.0,
        is_overdue=True,
    )

    assert _detect([parcel]) == []


def test_one_parcel_can_raise_two_kinds_at_once():
    """`59500007135457` on 2026-08-20: dark 9.7 days AND long overdue. Task rule
    3 dedupes per (parcel, kind), not per parcel — these are two different
    things to do about it."""
    parcel = _classified(
        tracking_number="59500007135457",
        state=STATE_NO_DATA,
        no_data_since=NOW - timedelta(days=9.7),
        is_overdue=True,
        days_overdue=14.2,
    )

    conditions = _detect([parcel])

    assert _kinds(conditions) == sorted([ALERT_NO_DATA_STUCK, ALERT_OVERDUE_LONG])
    assert {c.shipment_id for c in conditions} == {parcel.shipment_id}


def test_a_healthy_moving_parcel_raises_nothing():
    assert _detect([_classified()]) == []


def test_thresholds_move_every_boundary():
    """Task rule 2: the three numbers are configuration, not literals."""
    parcels = [
        _classified(state=STATE_NO_DATA, no_data_since=NOW - timedelta(days=3.5)),
        _classified(is_overdue=True, days_overdue=4.0),
        _classified(
            state=STATE_UNTRACKED,
            tracking_number=None,
            wb_created_at=NOW - timedelta(days=8),
        ),
    ]

    assert _detect(parcels) == []

    loosened = AlertThresholds(no_data_days=3, overdue_days=3, untracked_days=7)
    assert _kinds(_detect(parcels, thresholds=loosened)) == sorted(
        [ALERT_NO_DATA_STUCK, ALERT_OVERDUE_LONG, ALERT_UNTRACKED_AGING]
    )


def test_the_severity_order_covers_every_kind():
    """A kind missing from the order would sort last on the dashboard silently."""
    assert set(ALERT_KIND_ORDER) == {
        ALERT_DELIVERY_PROBLEM,
        ALERT_NO_DATA_STUCK,
        ALERT_OVERDUE_LONG,
        ALERT_UNTRACKED_AGING,
    }
    assert ALERT_KIND_ORDER[0] == ALERT_DELIVERY_PROBLEM


# ── thresholds from app_settings ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_thresholds_fall_back_to_the_evidence_backed_defaults():
    thresholds = await load_alert_thresholds(_db([_rows([])]))

    assert thresholds == AlertThresholds(
        no_data_days=DEFAULT_ALERT_NO_DATA_DAYS,
        overdue_days=DEFAULT_ALERT_OVERDUE_DAYS,
        untracked_days=DEFAULT_ALERT_UNTRACKED_DAYS,
    )
    assert (DEFAULT_ALERT_NO_DATA_DAYS, DEFAULT_ALERT_OVERDUE_DAYS) == (6, 7)
    assert DEFAULT_ALERT_UNTRACKED_DAYS == 14


@pytest.mark.asyncio
async def test_thresholds_read_overrides_in_one_query():
    db = _db(
        [
            _rows(
                [
                    _setting(WB_ALERT_NO_DATA_DAYS, "10"),
                    _setting(WB_ALERT_OVERDUE_DAYS, "3"),
                    _setting(WB_ALERT_UNTRACKED_DAYS, "21"),
                ]
            )
        ]
    )

    thresholds = await load_alert_thresholds(db)

    assert thresholds == AlertThresholds(10, 3, 21)
    assert db.execute.await_count == 1


@pytest.mark.asyncio
async def test_an_unparseable_threshold_falls_back_rather_than_raising():
    db = _db([_rows([_setting(WB_ALERT_NO_DATA_DAYS, "soon")])])

    thresholds = await load_alert_thresholds(db)

    assert thresholds.no_data_days == DEFAULT_ALERT_NO_DATA_DAYS


@pytest.mark.asyncio
async def test_a_zero_threshold_falls_back_instead_of_flagging_everything():
    db = _db([_rows([_setting(WB_ALERT_OVERDUE_DAYS, "0")])])

    thresholds = await load_alert_thresholds(db)

    assert thresholds.overdue_days == DEFAULT_ALERT_OVERDUE_DAYS


# ── sync_alerts: reconciliation ────────────────────────────────────────────


async def _sync(parcels, open_alerts=(), thresholds_rows=(), now=NOW):
    db = _db([_rows(list(thresholds_rows)), _scalars(list(open_alerts))])
    overview = TrackingOverview(counts={}, parcels=list(parcels))
    with patch.object(
        wb_tracking_service, "classify_parcels", AsyncMock(return_value=overview)
    ):
        summary = await sync_alerts(db, now=now)
    return summary, db


@pytest.mark.asyncio
async def test_a_new_condition_opens_exactly_one_alert():
    parcel = _classified(is_overdue=True, days_overdue=9.0)

    summary, db = await _sync([parcel])

    assert summary == {"alerts_opened": 1, "alerts_resolved": 0}
    (added,) = [c.args[0] for c in db.add.call_args_list]
    assert added.kind == ALERT_OVERDUE_LONG
    assert added.shipment_id == parcel.shipment_id
    assert added.raised_at == NOW
    assert added.last_seen_at == NOW
    assert added.resolved_at is None
    assert added.dismissed_at is None


@pytest.mark.asyncio
async def test_polling_an_unchanged_condition_re_raises_nothing():
    """Task rule 3. The open row is touched, not duplicated."""
    parcel = _classified(is_overdue=True, days_overdue=9.0)
    existing = _alert(shipment_id=parcel.shipment_id, kind=ALERT_OVERDUE_LONG)

    summary, db = await _sync([parcel], open_alerts=[existing])

    assert summary == {"alerts_opened": 0, "alerts_resolved": 0}
    db.add.assert_not_called()
    assert existing.last_seen_at == NOW
    assert existing.resolved_at is None


@pytest.mark.asyncio
async def test_an_open_alert_keeps_its_detail_current():
    parcel = _classified(is_overdue=True, days_overdue=12.0)
    existing = _alert(
        shipment_id=parcel.shipment_id,
        kind=ALERT_OVERDUE_LONG,
        detail="Прострочено 9 дн.",
    )

    await _sync([parcel], open_alerts=[existing])

    assert existing.detail == "Прострочено 12 дн."


@pytest.mark.asyncio
async def test_a_condition_that_disappears_closes_its_alert_by_itself():
    """The load-bearing half. Without auto-resolve the dashboard silts up with
    stale alerts and becomes the next surface nobody opens."""
    recovered = _classified()  # healthy again
    existing = _alert(shipment_id=recovered.shipment_id, kind=ALERT_NO_DATA_STUCK)

    summary, db = await _sync([recovered], open_alerts=[existing])

    assert summary == {"alerts_opened": 0, "alerts_resolved": 1}
    assert existing.resolved_at == NOW
    assert existing.resolution == RESOLUTION_CLEARED
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_a_parcel_that_leaves_the_window_closes_as_aged_out_not_cleared():
    """`untracked_aging` can never clear on evidence — WesternBid's status is
    creation-time only. Recording the 60-day exit as 'cleared' would claim
    knowledge we do not have."""
    existing = _alert(kind=ALERT_UNTRACKED_AGING)  # its parcel is not classified

    summary, _db_ = await _sync([], open_alerts=[existing])

    assert summary == {"alerts_opened": 0, "alerts_resolved": 1}
    assert existing.resolution == RESOLUTION_AGED_OUT


@pytest.mark.asyncio
async def test_a_dismissal_does_not_resurrect_while_the_condition_persists():
    """Task rule 5, first half. A dismissed alert is still OPEN, so it is
    touched rather than re-raised."""
    parcel = _classified(is_overdue=True, days_overdue=9.0)
    dismissed = _alert(
        shipment_id=parcel.shipment_id,
        kind=ALERT_OVERDUE_LONG,
        dismissed_at=NOW - timedelta(days=1),
        dismissed_by_id=uuid.uuid4(),
    )

    summary, db = await _sync([parcel], open_alerts=[dismissed])

    assert summary == {"alerts_opened": 0, "alerts_resolved": 0}
    db.add.assert_not_called()
    assert dismissed.resolved_at is None
    assert dismissed.last_seen_at == NOW


@pytest.mark.asyncio
async def test_a_dismissed_alert_closes_when_its_condition_finally_clears():
    dismisser = uuid.uuid4()
    recovered = _classified()
    dismissed = _alert(
        shipment_id=recovered.shipment_id,
        kind=ALERT_NO_DATA_STUCK,
        dismissed_at=NOW - timedelta(days=2),
        dismissed_by_id=dismisser,
    )

    summary, _db_ = await _sync([recovered], open_alerts=[dismissed])

    assert summary == {"alerts_opened": 0, "alerts_resolved": 1}
    assert dismissed.resolution == RESOLUTION_CLEARED
    # The who/when survives on the closed row: "dismissed by X, later cleared".
    assert dismissed.dismissed_by_id == dismisser
    assert dismissed.dismissed_at == NOW - timedelta(days=2)


@pytest.mark.asyncio
async def test_a_condition_that_recurs_after_closing_is_a_new_episode():
    """Task rule 5, second half. `59500007135457` went dark, recovered, and went
    dark again — the closed row does not block the second episode."""
    parcel = _classified(
        state=STATE_NO_DATA, no_data_since=NOW - timedelta(days=7)
    )
    # The previous episode is resolved, so it is not in the open set at all.
    summary, db = await _sync([parcel], open_alerts=[])

    assert summary == {"alerts_opened": 1, "alerts_resolved": 0}
    (added,) = [c.args[0] for c in db.add.call_args_list]
    assert added.kind == ALERT_NO_DATA_STUCK
    assert added.raised_at == NOW


@pytest.mark.asyncio
async def test_one_sync_can_open_and_resolve_at_the_same_time():
    fresh = _classified(state=STATE_PROBLEM, status_code="111")
    stale = _alert(kind=ALERT_OVERDUE_LONG)

    summary, db = await _sync([fresh], open_alerts=[stale])

    assert summary == {"alerts_opened": 1, "alerts_resolved": 1}
    assert stale.resolved_at == NOW
    assert db.add.call_count == 1


@pytest.mark.asyncio
async def test_sync_never_commits_or_flushes():
    """It runs inside `run_poll`, and both callers own the transaction."""
    parcel = _classified(is_overdue=True, days_overdue=9.0)

    _summary, db = await _sync([parcel])

    db.commit.assert_not_called()
    db.flush.assert_not_called()


@pytest.mark.asyncio
async def test_sync_honours_a_threshold_override_end_to_end():
    parcel = _classified(is_overdue=True, days_overdue=4.0)

    quiet, _ = await _sync([parcel])
    assert quiet["alerts_opened"] == 0

    loud, _ = await _sync(
        [parcel], thresholds_rows=[_setting(WB_ALERT_OVERDUE_DAYS, "3")]
    )
    assert loud["alerts_opened"] == 1


# ── run_poll integration ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_the_poll_reports_what_it_did_to_the_alerts():
    """Alert sync rides the poll pass (task rule 6) — one definition, the same
    two callers, so a manual Refresh updates the dashboard too."""
    db = _db([_scalars([]), _scalars([])])
    with patch.object(
        wb_tracking_service,
        "sync_alerts",
        AsyncMock(return_value={"alerts_opened": 2, "alerts_resolved": 1}),
    ) as sync:
        summary = await wb_tracking_service.run_poll(db)

    sync.assert_awaited_once()
    assert summary["alerts_opened"] == 2
    assert summary["alerts_resolved"] == 1


# ── endpoints ──────────────────────────────────────────────────────────────


def _parcel_row(**kwargs) -> WbParcel:
    defaults = dict(
        shipment_id=uuid.uuid4(),
        shipping_type="NovaPost",
        tracking_numbers=[
            {"Identifier": "WesternBid", "TrackingNumber": "WBX260000569570"},
            {"Identifier": "NovaPost", "TrackingNumber": "59500007147707"},
        ],
        recipient_name="Jane Doe",
        recipient_country_code="US",
    )
    defaults.update(kwargs)
    return WbParcel(**defaults)


def _list_db(pairs, polled_at=None):
    listing = MagicMock()
    listing.all.return_value = list(pairs)
    polled = MagicMock()
    polled.scalar_one.return_value = polled_at
    return _db([listing, polled])


@pytest.mark.asyncio
async def test_the_alert_list_carries_the_number_an_operator_can_act_on():
    parcel = _parcel_row()
    # `age_days` is computed against the real clock inside the route, so this
    # one fixture is anchored to it rather than to the frozen NOW above.
    alert = _alert(
        shipment_id=parcel.shipment_id,
        kind=ALERT_OVERDUE_LONG,
        raised_at=datetime.now(UTC) - timedelta(days=2),
    )
    polled_at = NOW - timedelta(hours=2)

    result = await list_parcel_alerts(
        current_user=MagicMock(), db=_list_db([(alert, parcel)], polled_at)
    )

    (row,) = result.alerts
    assert row.tracking_number == "59500007147707"
    assert row.recipient_name == "Jane Doe"
    assert row.carrier == "NovaPost"
    assert row.age_days == pytest.approx(2.0, abs=0.01)
    assert result.synced_at == polled_at


@pytest.mark.asyncio
async def test_an_untracked_alert_still_shows_a_number_to_check_by_hand():
    """WB-TRACK-2 OQ1 caught this exact trap once: telling an operator to check
    a parcel by hand while showing nothing to check with."""
    parcel = _parcel_row(
        shipping_type="UPS",
        tracking_numbers=[
            {"Identifier": "WesternBid", "TrackingNumber": "WBX260000559260"},
            {"Identifier": "UPS", "TrackingNumber": "1Z08W335D906259863"},
        ],
    )
    alert = _alert(shipment_id=parcel.shipment_id, kind=ALERT_UNTRACKED_AGING)

    result = await list_parcel_alerts(
        current_user=MagicMock(), db=_list_db([(alert, parcel)])
    )

    (row,) = result.alerts
    assert row.tracking_number is None
    assert "1Z08W335D906259863" in [n.TrackingNumber for n in row.tracking_numbers]


@pytest.mark.asyncio
async def test_alerts_are_ordered_worst_parcel_first_and_grouped_per_parcel():
    calm = _parcel_row()
    urgent = _parcel_row()
    pairs = [
        (_alert(shipment_id=calm.shipment_id, kind=ALERT_UNTRACKED_AGING), calm),
        (_alert(shipment_id=urgent.shipment_id, kind=ALERT_OVERDUE_LONG), urgent),
        (_alert(shipment_id=urgent.shipment_id, kind=ALERT_DELIVERY_PROBLEM), urgent),
    ]

    result = await list_parcel_alerts(
        current_user=MagicMock(), db=_list_db(pairs)
    )

    assert [a.kind for a in result.alerts] == [
        ALERT_DELIVERY_PROBLEM,
        ALERT_OVERDUE_LONG,
        ALERT_UNTRACKED_AGING,
    ]
    # The urgent parcel's two alerts are adjacent, not scattered.
    assert result.alerts[0].shipment_id == result.alerts[1].shipment_id


@pytest.mark.asyncio
async def test_dismissing_records_who_and_when():
    parcel = _parcel_row()
    alert = _alert(shipment_id=parcel.shipment_id)
    user = MagicMock()
    user.id = uuid.uuid4()
    db = _db()
    db.get = AsyncMock(side_effect=[alert, parcel])

    result = await dismiss_parcel_alert(
        alert_id=alert.id, current_user=user, db=db
    )

    assert alert.dismissed_by_id == user.id
    assert alert.dismissed_at is not None
    # Still OPEN — that is what blocks a re-raise while the condition persists.
    assert alert.resolved_at is None
    assert result.dismissed_by_id == user.id


@pytest.mark.asyncio
async def test_dismissing_twice_does_not_rewrite_who_dismissed_it():
    parcel = _parcel_row()
    first_user = uuid.uuid4()
    stamped_at = NOW - timedelta(days=1)
    alert = _alert(
        shipment_id=parcel.shipment_id,
        dismissed_at=stamped_at,
        dismissed_by_id=first_user,
    )
    second_user = MagicMock()
    second_user.id = uuid.uuid4()
    db = _db()
    db.get = AsyncMock(side_effect=[alert, parcel])

    await dismiss_parcel_alert(
        alert_id=alert.id, current_user=second_user, db=db
    )

    assert alert.dismissed_by_id == first_user
    assert alert.dismissed_at == stamped_at


@pytest.mark.asyncio
async def test_dismissing_an_alert_that_already_closed_itself_is_a_conflict():
    alert = _alert(resolved_at=NOW - timedelta(hours=1), resolution=RESOLUTION_CLEARED)
    db = _db()
    db.get = AsyncMock(return_value=alert)

    with pytest.raises(HTTPException) as exc:
        await dismiss_parcel_alert(
            alert_id=alert.id, current_user=MagicMock(), db=db
        )

    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_dismissing_an_unknown_alert_is_a_404():
    db = _db()
    db.get = AsyncMock(return_value=None)

    with pytest.raises(HTTPException) as exc:
        await dismiss_parcel_alert(
            alert_id=uuid.uuid4(), current_user=MagicMock(), db=db
        )

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_a_designer_neither_sees_nor_dismisses_alerts():
    """Task rule 4/8: alerts are OWNER+MANAGER, the same gate as the rest of
    this router and as `POST /tracking/refresh`."""
    checker = require_role(UserRole.OWNER, UserRole.MANAGER)
    designer = MagicMock()
    designer.role = UserRole.DESIGNER

    with pytest.raises(HTTPException) as exc:
        await checker(current_user=designer)

    assert exc.value.status_code == 403

    for role in (UserRole.OWNER, UserRole.MANAGER):
        allowed = MagicMock()
        allowed.role = role
        assert await checker(current_user=allowed) is allowed
