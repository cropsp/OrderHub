"""WB-TRACK-1 — Nova Poshta delivery tracking: client, recorder, classification.

Mock-based like the rest of the repo (httpx patched at the module boundary,
functions awaited directly with MagicMock dbs), plus a small live section at the
bottom.

**Why the live tests assert what they do.** During planning, one of the three
parcels task.md pinned as a verification fixture changed state within the same
day — it returned a full in-transit record in the morning and an empty stub in
the afternoon. So the live assertions are hard ONLY on a terminal state:
`59500007067740` is delivered (code 9), which cannot move, and everything about
it is pinned. In-flight parcels are illustrative: those tests assert shape
(resolves, has a code, dates parse) and never a specific status or date, so they
do not fail the day a parcel is delivered.
"""
import inspect
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import HTTPException
from tenacity import wait_none

from models.user import UserRole
from models.wb_parcel import WbParcel
from models.wb_tracking import WbParcelTracking, WbTrackingEvent
from routers.dependencies import require_role
from routers.westernbid import (
    get_tracking_events,
    get_tracking_overview,
    refresh_tracking,
)
from services import np_tracking, wb_tracking_service
from services.np_tracking import (
    NovaPoshtaTrackingClient,
    is_no_data,
    parse_np_datetime,
)
from services.nova_poshta import NovaPoshtaAPIError
from services.wb_tracking_service import (
    Candidate,
    DELIVERED_CODES,
    PROBLEM_CODES,
    STATE_DELIVERED,
    STATE_MOVING,
    STATE_NO_DATA,
    STATE_PROBLEM,
    STATE_UNTRACKED,
    classify_parcels,
    extract_novapost_number,
    record_poll,
    select_candidates,
)

UTC = timezone.utc


# ── helpers ────────────────────────────────────────────────

def _response(payload):
    r = MagicMock()
    r.json.return_value = payload
    r.raise_for_status = MagicMock()
    return r


def _async_client_cm(post_mock):
    client = MagicMock()
    client.post = post_mock
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=client)
    cm.__aexit__ = AsyncMock(return_value=None)
    return cm


def _scalars(items):
    r = MagicMock()
    r.scalars.return_value.all.return_value = list(items)
    return r


def _scalar(value):
    r = MagicMock()
    r.scalar_one_or_none.return_value = value
    return r


def _db(execute_results=()):
    db = MagicMock()
    db.execute = AsyncMock(side_effect=list(execute_results))
    db.add = MagicMock()
    return db


def _parcel(**kwargs):
    defaults = dict(
        shipment_id=uuid.uuid4(),
        shipping_type="NovaPost",
        tracking_numbers=[
            {"Identifier": "WesternBid", "TrackingNumber": "WBX260000569570"},
            {"Identifier": "NovaPost", "TrackingNumber": "59500007147707"},
        ],
        wb_created_at=datetime.now(UTC) - timedelta(days=2),
        wb_status="Parcel created",
        recipient_name="Jane Doe",
        recipient_country_code="US",
        order_id=None,
    )
    defaults.update(kwargs)
    return WbParcel(**defaults)


def _tracking(**kwargs):
    defaults = dict(
        tracking_number="59500007147707",
        shipment_id=uuid.uuid4(),
        carrier="NovaPost",
        status_code="5",
        status_text="Відправлення прямує до  Phoenix.",
        np_last_movement_at=datetime.now(UTC) - timedelta(hours=6),
        first_polled_at=datetime.now(UTC) - timedelta(days=1),
        last_polled_at=datetime.now(UTC) - timedelta(days=1),
    )
    defaults.update(kwargs)
    return WbParcelTracking(**defaults)


# A real record, trimmed to the fields the recorder reads. Captured live on
# 2026-08-05 from the delivered parcel task.md pins.
DELIVERED_RECORD = {
    "Number": "59500007067740",
    "StatusCode": "9",
    "Status": "Відправлення отримано",
    "DateCreated": "24-07-2026 10:15:35",
    "TrackingUpdateDate": "2026-08-03 00:22:47",
    "ScheduledDeliveryDate": "03-08-2026 05:00:00",
    "RecipientDateTime": "03.08.2026 00:22:47",
    "ActualDeliveryDate": "",
    "UndeliveryReasons": [],
    "CityRecipient": "Санта-Барбара",
    "InternationalDeliveryType": "Export",
}

# The stub NP returns for a number that no longer resolves — 9 keys instead of
# ~122, StatusCode 80 (undocumented), no dates at all.
STUB_RECORD = {
    "Number": "59500007112662",
    "StatusCode": "80",
    "Status": "",
    "PossibilityEUReturn": False,
    "FinalEUReturnDate": "",
    "EUReturnNumber": "",
    "ParentBranchCity": "",
    "ParentBranchName": "",
    "Edit": True,
}


# ── date parsing (OQ5 — all four formats are Kyiv wall-clock) ──

@pytest.mark.parametrize(
    "raw,expected",
    [
        # DateCreated / ScheduledDeliveryDate
        ("05-08-2026 16:36:53", datetime(2026, 8, 5, 13, 36, 53, tzinfo=UTC)),
        # TrackingUpdateDate
        ("2026-08-05 19:42:05", datetime(2026, 8, 5, 16, 42, 5, tzinfo=UTC)),
        # RecipientDateTime — the pinned delivery of 59500007067740
        ("03.08.2026 00:22:47", datetime(2026, 8, 2, 21, 22, 47, tzinfo=UTC)),
        # DateScan
        ("19:42 05.08.2026", datetime(2026, 8, 5, 16, 42, 0, tzinfo=UTC)),
    ],
)
def test_np_timestamps_are_kyiv_and_normalise_to_utc(raw, expected):
    assert parse_np_datetime(raw) == expected


def test_unparseable_timestamp_is_null_never_now():
    """A bad date must not silently become 'now' — the stalled signal subtracts
    against these values, so a fabricated one would hide a stuck parcel."""
    assert parse_np_datetime("yesterday-ish") is None
    assert parse_np_datetime("") is None
    assert parse_np_datetime(None) is None


# ── the no-data stub is detected structurally, not by code 80 ──

def test_stub_payload_is_detected_without_reading_the_status_code():
    assert is_no_data(STUB_RECORD) is True
    # Same shape, a different (equally undocumented) code — still no data.
    assert is_no_data({**STUB_RECORD, "StatusCode": "81"}) is True


def test_a_real_record_is_never_no_data():
    assert is_no_data(DELIVERED_RECORD) is False


# ── the client is keyless by construction (task rule 5) ────

@pytest.mark.asyncio
async def test_client_sends_an_empty_api_key():
    post = AsyncMock(return_value=_response({"success": True, "data": []}))
    with patch.object(np_tracking.httpx, "AsyncClient", return_value=_async_client_cm(post)):
        await NovaPoshtaTrackingClient().get_status_documents(["59500007147707"])

    body = post.await_args.kwargs["json"]
    assert body["apiKey"] == ""
    assert body["modelName"] == "TrackingDocument"
    assert body["calledMethod"] == "getStatusDocuments"
    assert body["methodProperties"]["Documents"] == [
        {"DocumentNumber": "59500007147707", "Phone": ""}
    ]


def test_the_client_cannot_be_given_a_credential():
    """No constructor argument can hold a key — that is the structural guarantee
    behind 'no API key, ever', and the reason this is not a method on
    NovaPoshtaClient, whose constructor demands one."""
    assert "__init__" not in vars(NovaPoshtaTrackingClient)
    with pytest.raises(TypeError):
        NovaPoshtaTrackingClient("an-api-key")


def test_the_module_never_reads_a_stored_credential():
    source = inspect.getsource(np_tracking)
    for forbidden in (
        "np_api_key_encrypted",
        "load_westernbid_credentials",
        "AppSetting",
        "decrypt_value",
        "encryption_service",
    ):
        assert forbidden not in source, forbidden


# ── batching: one request, not thirty (task rule 8) ────────

@pytest.mark.asyncio
async def test_the_whole_in_flight_set_is_one_request():
    post = AsyncMock(return_value=_response({"success": True, "data": []}))
    with patch.object(np_tracking.httpx, "AsyncClient", return_value=_async_client_cm(post)):
        await NovaPoshtaTrackingClient().get_status_documents(
            [f"5950000714{i:04d}" for i in range(77)]
        )
    assert post.await_count == 1


@pytest.mark.asyncio
async def test_more_than_a_hundred_numbers_split_into_full_batches():
    post = AsyncMock(return_value=_response({"success": True, "data": []}))
    with patch.object(np_tracking.httpx, "AsyncClient", return_value=_async_client_cm(post)):
        await NovaPoshtaTrackingClient().get_status_documents(
            [f"5950000714{i:04d}" for i in range(150)]
        )
    assert post.await_count == 2
    sizes = [
        len(c.kwargs["json"]["methodProperties"]["Documents"])
        for c in post.await_args_list
    ]
    assert sizes == [100, 50]


@pytest.mark.asyncio
async def test_api_level_failure_is_not_retried(monkeypatch):
    monkeypatch.setattr(NovaPoshtaTrackingClient._post.retry, "wait", wait_none())
    post = AsyncMock(
        return_value=_response({"success": False, "errors": ["API key expired"]})
    )
    with patch.object(np_tracking.httpx, "AsyncClient", return_value=_async_client_cm(post)):
        with pytest.raises(NovaPoshtaAPIError):
            await NovaPoshtaTrackingClient().get_status_documents(["59500007147707"])
    assert post.await_count == 1


# ── OQ1: selecting the Nova Poshta number ──────────────────

def test_the_novapost_element_is_selected_not_the_wbx_one():
    assert extract_novapost_number(_parcel()) == "59500007147707"


def test_a_ups_parcel_has_no_novapost_number():
    """`Identifier` is a label, not a carrier: the one USPS/ConsolidationOptimum
    number in prod is filed under "UPS" too. Neither is trackable here."""
    for number in ("1Z08W335D906259863", "92612902711411543487976366"):
        parcel = _parcel(
            shipping_type="UPS",
            tracking_numbers=[
                {"Identifier": "WesternBid", "TrackingNumber": "WBX000000241486"},
                {"Identifier": "UPS", "TrackingNumber": number},
            ],
        )
        assert extract_novapost_number(parcel) is None


def test_a_parcel_with_only_a_wb_number_has_none():
    """One real parcel (canceled, 2026-07-27) carries a single WBX element."""
    parcel = _parcel(
        tracking_numbers=[
            {"Identifier": "WesternBid", "TrackingNumber": "WBX100000000001"}
        ],
        wb_status="Parcel canceled",
    )
    assert extract_novapost_number(parcel) is None


def test_malformed_tracking_json_does_not_crash_selection():
    assert extract_novapost_number(_parcel(tracking_numbers=[])) is None
    assert extract_novapost_number(_parcel(tracking_numbers=["59500007147707"])) is None
    assert (
        extract_novapost_number(
            _parcel(tracking_numbers=[{"Identifier": "NovaPost", "TrackingNumber": ""}])
        )
        is None
    )


# ── OQ3: who is polled, and how a parcel leaves the set ────

@pytest.mark.asyncio
async def test_untrackable_and_terminal_parcels_are_not_polled():
    tracked = _parcel()
    ups = _parcel(
        shipping_type="UPS",
        tracking_numbers=[{"Identifier": "UPS", "TrackingNumber": "1Z08"}],
    )
    delivered = _parcel(
        tracking_numbers=[
            {"Identifier": "NovaPost", "TrackingNumber": "59500007067740"}
        ]
    )
    stopped = _tracking(
        tracking_number="59500007067740",
        polling_stopped_at=datetime.now(UTC),
        stopped_reason="delivered",
    )

    db = _db([_scalars([tracked, ups, delivered]), _scalars([stopped])])
    candidates = await select_candidates(db)

    assert [c.tracking_number for c in candidates] == ["59500007147707"]


@pytest.mark.asyncio
async def test_a_parcel_older_than_the_window_is_retired_loudly(caplog):
    old = _parcel(wb_created_at=datetime.now(UTC) - timedelta(days=90))
    tracking = _tracking()
    db = _db([_scalars([old]), _scalars([tracking])])

    with caplog.at_level("INFO", logger="services.wb_tracking_service"):
        candidates = await select_candidates(db)

    assert candidates == []
    assert tracking.polling_stopped_at is not None
    assert tracking.stopped_reason == "aged_out"
    assert any("retired" in r.getMessage() for r in caplog.records)


# ── OQ2 / rule 2: transitions, not snapshots ───────────────

def _candidate(parcel=None, tracking=None, number="59500007147707"):
    parcel = parcel or _parcel()
    return Candidate(parcel=parcel, tracking_number=number, tracking=tracking)


@pytest.mark.asyncio
async def test_repolling_an_unchanged_parcel_writes_no_event():
    tracking = _tracking(status_code="5", status_text="Відправлення прямує до  Phoenix.")
    db = _db()
    record = {
        "Number": "59500007147707",
        "StatusCode": "5",
        "Status": "Відправлення прямує до  Phoenix.",
        "TrackingUpdateDate": "2026-08-05 19:42:05",
    }

    summary = await record_poll(db, [_candidate(tracking=tracking)], [record])

    assert db.add.call_count == 0
    assert summary["changed"] == 0
    assert summary["polled"] == 1


@pytest.mark.asyncio
async def test_a_changed_status_writes_exactly_one_event():
    tracking = _tracking(status_code="4", status_text="Відправлення у м. Бориспіль")
    db = _db()
    record = {
        "Number": "59500007147707",
        "StatusCode": "5",
        "Status": "Відправлення прямує до  Phoenix.",
        "TrackingUpdateDate": "2026-08-05 19:42:05",
    }

    summary = await record_poll(db, [_candidate(tracking=tracking)], [record])

    assert db.add.call_count == 1
    event = db.add.call_args.args[0]
    assert (event.status_code, event.status_text) == (
        "5",
        "Відправлення прямує до  Phoenix.",
    )
    assert event.observed_at is not None
    assert summary["changed"] == 1
    assert tracking.status_code == "5"


@pytest.mark.asyncio
async def test_the_same_code_reaching_a_new_city_is_a_transition():
    """`status_text` carries the city, so code 5 → code 5 can still be movement."""
    tracking = _tracking(status_code="5", status_text="Відправлення прямує до  Phoenix.")
    db = _db()
    record = {
        "Number": "59500007147707",
        "StatusCode": "5",
        "Status": "Відправлення прямує до  Chicago.",
        "TrackingUpdateDate": "2026-08-05 19:42:05",
    }

    await record_poll(db, [_candidate(tracking=tracking)], [record])

    assert db.add.call_count == 1


@pytest.mark.asyncio
async def test_a_first_poll_creates_the_row_and_its_first_event():
    db = _db()
    summary = await record_poll(
        db,
        [_candidate(number="59500007067740")],
        [DELIVERED_RECORD],
    )
    added = [c.args[0] for c in db.add.call_args_list]
    assert summary["created"] == 1
    assert isinstance(added[0], WbParcelTracking)
    assert len(added) == 2  # the row, then its first transition


# ── the no-data stub keeps the last known status ───────────

@pytest.mark.asyncio
async def test_a_stub_keeps_the_last_status_flags_it_and_keeps_polling(caplog):
    tracking = _tracking(status_code="5", status_text="Прямує до Garnet Valley")
    db = _db()

    with caplog.at_level("INFO", logger="services.wb_tracking_service"):
        summary = await record_poll(
            db, [_candidate(tracking=tracking, number="59500007112662")], [STUB_RECORD]
        )

    # Last resolved status survives — it is all we know about where it got to.
    assert tracking.status_code == "5"
    assert tracking.status_text == "Прямує до Garnet Valley"
    assert tracking.no_data_since is not None
    # Still polled tomorrow: no terminal stamp.
    assert tracking.polling_stopped_at is None
    assert summary["no_data"] == 1
    # Exactly one event on entering the state.
    assert db.add.call_count == 1


@pytest.mark.asyncio
async def test_a_second_stub_does_not_write_a_second_event():
    tracking = _tracking(no_data_since=datetime.now(UTC) - timedelta(days=1))
    db = _db()
    await record_poll(
        db, [_candidate(tracking=tracking, number="59500007112662")], [STUB_RECORD]
    )
    assert db.add.call_count == 0


@pytest.mark.asyncio
async def test_recovery_from_no_data_clears_the_flag():
    tracking = _tracking(
        status_code="5",
        status_text="Прямує до Garnet Valley",
        no_data_since=datetime.now(UTC) - timedelta(days=1),
    )
    db = _db()
    record = {
        "Number": "59500007112662",
        "StatusCode": "6",
        "Status": "Відправлення у  Garnet Valley. Очікуйте повідомлення про прибуття",
        "TrackingUpdateDate": "2026-08-06 09:00:00",
    }
    await record_poll(db, [_candidate(tracking=tracking, number="59500007112662")], [record])
    assert tracking.no_data_since is None
    assert tracking.status_code == "6"


@pytest.mark.asyncio
async def test_a_document_missing_from_the_response_leaves_the_row_alone():
    tracking = _tracking(status_code="5")
    db = _db()
    summary = await record_poll(db, [_candidate(tracking=tracking)], [])
    assert summary["missing"] == 1
    assert tracking.status_code == "5"
    assert db.add.call_count == 0


# ── delivery is terminal ───────────────────────────────────

@pytest.mark.asyncio
async def test_delivery_stops_polling_and_uses_recipient_date_time():
    tracking = _tracking(tracking_number="59500007067740", status_code="6")
    db = _db()

    await record_poll(
        db, [_candidate(tracking=tracking, number="59500007067740")], [DELIVERED_RECORD]
    )

    assert tracking.status_code == "9"
    # RecipientDateTime 03.08.2026 00:22:47 Kyiv, NOT ActualDeliveryDate (empty).
    assert tracking.np_delivered_at == datetime(2026, 8, 2, 21, 22, 47, tzinfo=UTC)
    assert tracking.polling_stopped_at is not None
    assert tracking.stopped_reason == "delivered"


def test_only_documented_closed_codes_are_terminal():
    assert DELIVERED_CODES == {"9", "10", "11"}
    # The codes we actually see in flight must never read as delivered.
    for code in ("1", "4", "5", "6", "101", "111", "115", "121", "80", "999"):
        assert code not in DELIVERED_CODES


def test_the_observed_failure_code_is_a_problem_not_movement():
    assert "111" in PROBLEM_CODES
    assert not PROBLEM_CODES & DELIVERED_CODES


# ── classification + the two attention signals ─────────────

async def _classify(parcels, tracking_rows, stalled_days=None, orders=()):
    results = [_scalar(stalled_days), _scalars(parcels), _scalars(tracking_rows)]
    if any(p.order_id for p in parcels):
        # The order lookup selects columns, not entities, so its result is
        # iterated directly rather than through .scalars().
        results.append(list(orders))
    return await classify_parcels(_db(results))


@pytest.mark.asyncio
async def test_overdue_is_flagged_even_when_the_parcel_is_moving_daily():
    """Belews Creek, 2026-08-05: scanned this morning, 11.9 days past its
    scheduled date. Fresh movement, badly overdue — `stalled` alone misses it."""
    parcel = _parcel()
    tracking = _tracking(
        status_code="6",
        np_scheduled_delivery_at=datetime.now(UTC) - timedelta(days=11.9),
        np_last_movement_at=datetime.now(UTC) - timedelta(hours=9),
    )
    overview = await _classify([parcel], [tracking])

    (p,) = overview.parcels
    assert p.state == STATE_MOVING
    assert p.is_overdue is True
    assert p.is_stalled is False
    assert p.days_overdue == pytest.approx(11.9, abs=0.1)


@pytest.mark.asyncio
async def test_stalled_is_flagged_inside_a_generous_delivery_window():
    """The inverse case: the promise has not expired yet, but nothing has
    scanned the parcel in a week."""
    parcel = _parcel()
    tracking = _tracking(
        status_code="121",
        np_scheduled_delivery_at=datetime.now(UTC) + timedelta(days=3),
        np_last_movement_at=datetime.now(UTC) - timedelta(days=7.1),
    )
    overview = await _classify([parcel], [tracking])

    (p,) = overview.parcels
    assert p.is_stalled is True
    assert p.is_overdue is False
    assert p.days_since_movement == pytest.approx(7.1, abs=0.1)


@pytest.mark.asyncio
async def test_a_healthy_parcel_raises_neither_signal():
    parcel = _parcel()
    tracking = _tracking(
        status_code="5",
        np_scheduled_delivery_at=datetime.now(UTC) + timedelta(days=5),
        np_last_movement_at=datetime.now(UTC) - timedelta(hours=4),
    )
    overview = await _classify([parcel], [tracking])

    (p,) = overview.parcels
    assert (p.state, p.is_overdue, p.is_stalled) == (STATE_MOVING, False, False)


@pytest.mark.asyncio
async def test_the_stalled_threshold_comes_from_configuration():
    parcel = _parcel()
    tracking = _tracking(np_last_movement_at=datetime.now(UTC) - timedelta(days=4))

    default_view = await _classify([parcel], [tracking])
    assert default_view.stalled_days == 3
    assert default_view.parcels[0].is_stalled is True

    relaxed = await _classify([parcel], [tracking], stalled_days="10")
    assert relaxed.stalled_days == 10
    assert relaxed.parcels[0].is_stalled is False


@pytest.mark.asyncio
async def test_a_nonsense_threshold_falls_back_to_the_default():
    parcel = _parcel()
    tracking = _tracking()
    for bad in ("soon", "0", "-3"):
        overview = await _classify([parcel], [tracking], stalled_days=bad)
        assert overview.stalled_days == 3


@pytest.mark.asyncio
async def test_a_delivered_parcel_raises_no_attention_signal():
    """Its scheduled date is in the past by definition — that must not read as
    overdue once it has actually arrived."""
    parcel = _parcel()
    tracking = _tracking(
        status_code="9",
        status_text="Відправлення отримано",
        np_scheduled_delivery_at=datetime.now(UTC) - timedelta(days=4),
        np_last_movement_at=datetime.now(UTC) - timedelta(days=4),
        np_delivered_at=datetime.now(UTC) - timedelta(days=4),
    )
    overview = await _classify([parcel], [tracking])

    (p,) = overview.parcels
    assert p.state == STATE_DELIVERED
    assert (p.is_overdue, p.is_stalled) == (False, False)
    assert (p.days_overdue, p.days_since_movement) == (None, None)


@pytest.mark.asyncio
async def test_a_failed_delivery_attempt_is_its_own_state():
    parcel = _parcel()
    tracking = _tracking(
        status_code="111",
        status_text="Невдала спроба доставки через відсутність Одержувача",
    )
    overview = await _classify([parcel], [tracking])
    assert overview.parcels[0].state == STATE_PROBLEM


@pytest.mark.asyncio
async def test_an_unknown_code_is_moving_never_delivered():
    parcel = _parcel()
    tracking = _tracking(status_code="777", status_text="Щось нове")
    overview = await _classify([parcel], [tracking])
    assert overview.parcels[0].state == STATE_MOVING


@pytest.mark.asyncio
async def test_no_data_outranks_the_stale_code_it_leaves_behind():
    parcel = _parcel()
    tracking = _tracking(status_code="5", no_data_since=datetime.now(UTC))
    overview = await _classify([parcel], [tracking])

    (p,) = overview.parcels
    assert p.state == STATE_NO_DATA
    # The last known status still travels, so the operator sees where it got to.
    assert p.status_text == "Відправлення прямує до  Phoenix."
    assert p.no_data_since is not None


@pytest.mark.asyncio
async def test_untrackable_parcels_are_named_never_omitted():
    """A monitor that silently drops ~8% of parcels is worse than one that says
    'check these by hand'."""
    ups = _parcel(
        shipping_type="UPS",
        tracking_numbers=[
            {"Identifier": "WesternBid", "TrackingNumber": "WBX0"},
            {"Identifier": "UPS", "TrackingNumber": "1Z08W335D906259863"},
        ],
    )
    usps = _parcel(
        shipping_type="ConsolidationOptimum",
        tracking_numbers=[{"Identifier": "UPS", "TrackingNumber": "9261290271141"}],
    )
    overview = await _classify([ups, usps], [])

    assert overview.counts[STATE_UNTRACKED] == 2
    assert {p.state for p in overview.parcels} == {STATE_UNTRACKED}
    # The carrier survives so a later UPS reader is a new reader, not a migration.
    assert {p.carrier for p in overview.parcels} == {"UPS", "ConsolidationOptimum"}
    assert all(p.tracking_number is None for p in overview.parcels)


@pytest.mark.asyncio
async def test_counts_cover_every_state_and_both_signals():
    healthy = _parcel()
    stuck = _parcel(
        tracking_numbers=[
            {"Identifier": "NovaPost", "TrackingNumber": "59500007067712"}
        ]
    )
    ups = _parcel(
        shipping_type="UPS",
        tracking_numbers=[{"Identifier": "UPS", "TrackingNumber": "1Z08"}],
    )
    overview = await _classify(
        [healthy, stuck, ups],
        [
            _tracking(np_last_movement_at=datetime.now(UTC) - timedelta(hours=2)),
            _tracking(
                tracking_number="59500007067712",
                status_code="6",
                np_scheduled_delivery_at=datetime.now(UTC) - timedelta(days=7.9),
                np_last_movement_at=datetime.now(UTC) - timedelta(days=4.97),
            ),
        ],
    )

    assert overview.counts["total"] == 3
    assert overview.counts[STATE_MOVING] == 2
    assert overview.counts[STATE_UNTRACKED] == 1
    assert overview.counts["overdue"] == 1
    assert overview.counts["stalled"] == 1


@pytest.mark.asyncio
async def test_the_order_link_is_carried_when_wb_2_has_populated_one():
    """`order_id` is NULL for most parcels until WB-2, so the page needs the few
    that have one to arrive already resolved rather than as a second lookup."""
    order_id = uuid.uuid4()
    parcel = _parcel(order_id=order_id)
    overview = await _classify(
        [parcel],
        [_tracking()],
        orders=[SimpleNamespace(id=order_id, order_number="91890_1797")],
    )
    (p,) = overview.parcels
    assert (p.order_id, p.order_number) == (order_id, "91890_1797")


@pytest.mark.asyncio
async def test_parcels_outside_the_window_leave_the_monitor():
    fresh = _parcel()
    ancient = _parcel(wb_created_at=datetime.now(UTC) - timedelta(days=200))
    overview = await _classify([fresh, ancient], [_tracking()])
    assert overview.counts["total"] == 1


@pytest.mark.asyncio
async def test_a_parcel_awaiting_its_first_poll_is_not_reported_as_delivered():
    overview = await _classify([_parcel()], [])
    (p,) = overview.parcels
    assert p.state == STATE_MOVING
    assert p.status_code is None
    assert overview.polled_at is None


# ── access control (OQ6) ───────────────────────────────────

@pytest.mark.asyncio
async def test_tracking_is_forbidden_to_a_designer():
    checker = require_role(UserRole.OWNER, UserRole.MANAGER)
    designer = MagicMock()
    designer.role = UserRole.DESIGNER
    with pytest.raises(HTTPException) as exc:
        await checker(current_user=designer)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_tracking_is_allowed_to_manager_and_owner():
    checker = require_role(UserRole.OWNER, UserRole.MANAGER)
    for role in (UserRole.OWNER, UserRole.MANAGER):
        user = MagicMock()
        user.role = role
        assert await checker(current_user=user) is user


# ── WB-TRACK-2: what the monitoring page reads ─────────────

def _untracked_parcel(**kwargs):
    """A UPS parcel: no Nova Poshta number, so `tracking_number` is None."""
    defaults = dict(
        shipping_type="UPS",
        tracking_numbers=[
            {"Identifier": "WesternBid", "TrackingNumber": "WBX000000241486"},
            {"Identifier": "UPS", "TrackingNumber": "1Z08W335D906259863"},
        ],
    )
    defaults.update(kwargs)
    return _parcel(**defaults)


def test_an_untracked_parcel_still_exposes_a_number_to_check_by_hand():
    """The whole point of naming untracked parcels instead of dropping them: the
    NP number is None for all 7 of them, so without this the operator is told to
    "check by hand" and given nothing to check."""
    parcel = _untracked_parcel()
    assert extract_novapost_number(parcel) is None
    assert wb_tracking_service.carrier_tracking_numbers(parcel) == [
        {"Identifier": "WesternBid", "TrackingNumber": "WBX000000241486"},
        {"Identifier": "UPS", "TrackingNumber": "1Z08W335D906259863"},
    ]


def test_malformed_tracking_json_does_not_crash_the_page_either():
    """Same defensiveness as extract_novapost_number — bare strings have been
    seen in this JSONB column, and a monitor must not 500 on one."""
    parcel = _parcel(
        tracking_numbers=[
            "59500007147707",
            {"Identifier": "NovaPost", "TrackingNumber": ""},
            {"TrackingNumber": "  1Z08W335D906259863  "},
        ]
    )
    assert wb_tracking_service.carrier_tracking_numbers(parcel) == [
        {"Identifier": None, "TrackingNumber": "1Z08W335D906259863"}
    ]


@pytest.mark.asyncio
async def test_the_classification_carries_the_wb_leg_and_every_number():
    """`Parcel canceled` is the case rule 1 protects: no carrier number, so it
    classifies `untracked`, and WB's own status is the ONLY thing that explains
    it. Verified against prod 2026-08-06 (shipment f2d61301…)."""
    canceled = _parcel(
        tracking_numbers=[
            {"Identifier": "WesternBid", "TrackingNumber": "WBX100000000001"}
        ],
        wb_status="Parcel canceled",
        payment_status="Paid",
    )
    overview = await _classify([canceled], [])

    (p,) = overview.parcels
    assert p.state == STATE_UNTRACKED
    assert p.wb_status == "Parcel canceled"
    assert p.payment_status == "Paid"
    assert p.tracking_numbers == [
        {"Identifier": "WesternBid", "TrackingNumber": "WBX100000000001"}
    ]


@pytest.mark.asyncio
async def test_a_poll_with_nothing_to_track_makes_no_request():
    db = _db([_scalars([]), _scalars([])])
    with patch.object(wb_tracking_service, "NovaPoshtaTrackingClient") as client_cls:
        summary = await wb_tracking_service.run_poll(db)

    client_cls.assert_not_called()
    assert summary == {
        "polled": 0,
        "created": 0,
        "changed": 0,
        "delivered": 0,
        "no_data": 0,
        "missing": 0,
    }


@pytest.mark.asyncio
async def test_one_poll_is_one_batched_request_for_every_candidate():
    parcels = [
        _parcel(),
        _parcel(
            tracking_numbers=[
                {"Identifier": "NovaPost", "TrackingNumber": "59500007112662"}
            ]
        ),
        _untracked_parcel(),
    ]
    db = _db([_scalars(parcels), _scalars([])])
    client = MagicMock()
    client.get_status_documents = AsyncMock(return_value=[])

    with patch.object(
        wb_tracking_service, "NovaPoshtaTrackingClient", MagicMock(return_value=client)
    ):
        await wb_tracking_service.run_poll(db)

    client.get_status_documents.assert_awaited_once_with(
        ["59500007147707", "59500007112662"]
    )


@pytest.mark.asyncio
async def test_the_manual_refresh_and_the_daily_job_share_one_poll():
    """The write-path twin of the single-classification rule: two callers, one
    definition. A second poll implementation is how the button and the job would
    come to disagree about what a poll does."""
    import scheduler

    summary = {
        "polled": 3,
        "created": 0,
        "changed": 1,
        "delivered": 0,
        "no_data": 0,
        "missing": 0,
    }

    with patch.object(
        wb_tracking_service, "load_last_polled_at", AsyncMock(return_value=None)
    ), patch.object(
        wb_tracking_service, "run_poll", AsyncMock(return_value=summary)
    ) as route_poll:
        result = await refresh_tracking(current_user=MagicMock(), db=MagicMock())
    assert route_poll.await_count == 1
    assert result.changed == 1

    session = MagicMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    factory = MagicMock(return_value=_async_client_cm(None))
    factory.return_value.__aenter__ = AsyncMock(return_value=session)

    with patch.object(scheduler, "async_session_factory", factory), patch.object(
        wb_tracking_service, "run_poll", AsyncMock(return_value=summary)
    ) as job_poll:
        await scheduler.run_wb_tracking_poll()
    assert job_poll.await_count == 1
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_a_refresh_inside_the_cooldown_is_refused_by_the_server():
    """A disabled button is a hint. This route is reachable by anyone who can
    open the page, so the throttle has to live here."""
    with patch.object(
        wb_tracking_service,
        "load_last_polled_at",
        AsyncMock(return_value=datetime.now(UTC) - timedelta(minutes=1)),
    ), patch.object(wb_tracking_service, "run_poll", AsyncMock()) as poll:
        with pytest.raises(HTTPException) as exc:
            await refresh_tracking(current_user=MagicMock(), db=MagicMock())

    assert exc.value.status_code == 429
    assert "Retry-After" in exc.value.headers
    poll.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_refresh_is_allowed_once_the_data_is_stale():
    stale = datetime.now(UTC) - timedelta(
        minutes=wb_tracking_service.MANUAL_POLL_COOLDOWN_MINUTES + 1
    )
    with patch.object(
        wb_tracking_service, "load_last_polled_at", AsyncMock(return_value=stale)
    ), patch.object(
        wb_tracking_service,
        "run_poll",
        AsyncMock(
            return_value={
                "polled": 1,
                "created": 0,
                "changed": 0,
                "delivered": 0,
                "no_data": 0,
                "missing": 0,
            }
        ),
    ) as poll:
        await refresh_tracking(current_user=MagicMock(), db=MagicMock())

    poll.assert_awaited_once()


async def _route_overview(parcels, tracking_rows, **kwargs):
    overview = await _classify(parcels, tracking_rows)
    with patch.object(
        wb_tracking_service, "classify_parcels", AsyncMock(return_value=overview)
    ):
        return await get_tracking_overview(
            current_user=MagicMock(), db=MagicMock(), **kwargs
        )


@pytest.mark.asyncio
async def test_the_page_asks_for_every_state_except_delivered_in_one_call():
    delivered = _parcel()
    moving = _parcel(
        tracking_numbers=[
            {"Identifier": "NovaPost", "TrackingNumber": "59500007112662"}
        ]
    )
    untracked = _untracked_parcel()
    rows = [
        _tracking(status_code="9", shipment_id=delivered.shipment_id),
        _tracking(tracking_number="59500007112662", shipment_id=moving.shipment_id),
    ]

    result = await _route_overview(
        [delivered, moving, untracked],
        rows,
        state="moving,problem,no_data,untracked",
        limit=None,
        offset=0,
    )

    assert {p.state for p in result.parcels} == {STATE_MOVING, STATE_UNTRACKED}
    # counts still describe the FULL set — the collapsed "Delivered" header on
    # the page shows a number for rows this call deliberately did not fetch.
    assert result.counts["delivered"] == 1
    assert result.counts["total"] == 3


@pytest.mark.asyncio
async def test_the_delivered_group_pages_without_shrinking_the_counts():
    parcels = [_parcel() for _ in range(3)]
    rows = [
        _tracking(
            tracking_number=f"5950000714770{i}",
            shipment_id=p.shipment_id,
            status_code="9",
        )
        for i, p in enumerate(parcels)
    ]
    for i, p in enumerate(parcels):
        p.tracking_numbers = [
            {"Identifier": "NovaPost", "TrackingNumber": f"5950000714770{i}"}
        ]

    page = await _route_overview(parcels, rows, state="delivered", limit=2, offset=0)
    assert len(page.parcels) == 2
    assert page.counts["delivered"] == 3

    tail = await _route_overview(parcels, rows, state="delivered", limit=2, offset=2)
    assert len(tail.parcels) == 1
    assert tail.counts["delivered"] == 3


@pytest.mark.asyncio
async def test_an_unpaginated_caller_still_sees_the_whole_set():
    """`check_parcel_delivery` sends neither limit nor offset and must keep
    seeing exactly what it saw before WB-TRACK-2."""
    parcels = [_parcel(), _untracked_parcel()]
    result = await _route_overview(parcels, [_tracking()], state=None, limit=None, offset=0)
    assert len(result.parcels) == 2


@pytest.mark.asyncio
async def test_the_transition_log_reads_forwards():
    """"How did it get here" reads oldest-first."""
    events = [
        WbTrackingEvent(
            tracking_number="59500007147707",
            status_code="4",
            status_text="Відправлення прямує до  Phoenix.",
            observed_at=datetime.now(UTC) - timedelta(days=2),
        ),
        WbTrackingEvent(
            tracking_number="59500007147707",
            status_code="111",
            status_text="Невдала спроба доставки",
            observed_at=datetime.now(UTC),
        ),
    ]
    db = _db([_scalar("59500007147707"), _scalars(events)])

    result = await get_tracking_events(
        tracking_number="59500007147707", current_user=MagicMock(), db=db
    )

    assert [e.status_code for e in result] == ["4", "111"]
    assert result[0].observed_at < result[1].observed_at


@pytest.mark.asyncio
async def test_history_for_a_number_we_never_tracked_is_a_404():
    db = _db([_scalar(None)])
    with pytest.raises(HTTPException) as exc:
        await get_tracking_events(
            tracking_number="1Z08W335D906259863", current_user=MagicMock(), db=db
        )
    assert exc.value.status_code == 404


# ── live: the shipping code path against the real endpoint ──
#
# Hard assertions ONLY on the terminal parcel (see the module docstring).

async def _live(numbers):
    try:
        return await NovaPoshtaTrackingClient().get_status_documents(numbers)
    except (httpx.HTTPError, NovaPoshtaAPIError) as exc:
        pytest.skip(f"Nova Poshta unreachable: {exc}")


@pytest.mark.asyncio
async def test_live_delivered_parcel_reproduces_exactly():
    """59500007067740 is delivered (code 9, terminal) — it cannot move, so every
    value here is pinned. Runs through record_poll, not a scratch request."""
    records = await _live(["59500007067740"])
    assert len(records) == 1

    tracking = _tracking(tracking_number="59500007067740", status_code=None, status_text=None)
    db = _db()
    await record_poll(
        db,
        [Candidate(parcel=_parcel(), tracking_number="59500007067740", tracking=tracking)],
        records,
    )

    assert tracking.status_code == "9"
    assert tracking.status_text == "Відправлення отримано"
    assert tracking.np_delivered_at == datetime(2026, 8, 2, 21, 22, 47, tzinfo=UTC)
    assert tracking.stopped_reason == "delivered"


@pytest.mark.asyncio
async def test_live_in_flight_parcels_resolve_without_pinning_their_state():
    """Illustrative fixtures only: assert the SHAPE, never a status or date.
    One of these was delivered days after task.md pinned it as 'in transit'."""
    numbers = ["59500007147419", "59500007141107"]
    records = await _live(numbers)

    # Two documents, one request (task rule 8).
    assert {r["Number"] for r in records} == set(numbers)
    for record in records:
        if is_no_data(record):
            continue  # a number may stop resolving; that is a state, not a failure
        assert str(record["StatusCode"]).strip()
        assert parse_np_datetime(record.get("TrackingUpdateDate")) is not None


@pytest.mark.asyncio
async def test_live_keyless_endpoint_masks_the_recipient_name():
    """OQ6 evidence: NP returns a city but never a name, so tracking rows carry
    less identity than the parcel mirror they hang off."""
    records = await _live(["59500007067740"])
    record = records[0]
    assert record.get("CityRecipient")
    assert not (record.get("RecipientFullName") or "").strip()
    assert not (record.get("RecipientAddress") or "").strip()
