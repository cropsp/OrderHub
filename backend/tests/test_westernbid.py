"""WB-1 — WesternBid client, poller, and access tests.

Mock-based, matching the repo's router/service test style (httpx mocked at the
module boundary; functions awaited directly with AsyncMock dbs).
"""
import logging
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import HTTPException
from tenacity import wait_none

import scheduler
from models.user import UserRole
from routers.dependencies import require_role
from services.westernbid import (
    WesternBidAPIError,
    WesternBidClient,
    WesternBidLabelNotReady,
    WesternBidTransientError,
    find_candidate_parcels,
    normalize_wb_datetime,
    rank_candidates,
    resolve_label_type,
)


# ── helpers ────────────────────────────────────────────────

def _response(json_payload):
    r = MagicMock()
    r.json.return_value = json_payload
    r.raise_for_status = MagicMock()
    return r


def _async_client_cm(get_mock):
    """Mock context manager whose client's .get is get_mock."""
    client = MagicMock()
    client.get = get_mock
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=client)
    cm.__aexit__ = AsyncMock(return_value=None)
    return cm, client


SAMPLE_ITEM = {
    "Id": "87c4a479-e185-4f57-8869-f30d7a7cad41",
    "ShippingType": "ConsolidationPlus",
    "CarrierType": "UPS",
    "ShippingServiceType": "UPSWWEconomy",
    "CreatedDate": "2026-04-27T06:55:05.4328732-05:00",
    "Package": {"weight": "1.2"},
    "TrackingNumbers": ["1Z999"],
    "RecipientCountryCode": "DE",
    "RecipientPostalCode": "25335",
    "RecipientName": "Gizem Yilmaz",
    "PaymentStatus": "Paid",
    "Status": "Parcel created",
}


# ── normalize_wb_datetime (task rule 8) ────────────────────

def test_normalize_wb_datetime_converts_offset_to_utc():
    # 06:55:05 -05:00 == 11:55:05 UTC. 7-digit fractional seconds must not break parsing.
    dt = normalize_wb_datetime("2026-04-27T06:55:05.4328732-05:00")
    assert dt is not None
    assert dt.tzinfo is not None
    assert dt.utcoffset() == timezone.utc.utcoffset(None)
    assert (dt.hour, dt.minute, dt.second) == (11, 55, 5)


def test_normalize_wb_datetime_assumes_utc_when_naive():
    dt = normalize_wb_datetime("2026-04-27T06:55:05")
    assert dt.tzinfo == timezone.utc
    assert dt.hour == 6


def test_normalize_wb_datetime_none_passthrough():
    assert normalize_wb_datetime(None) is None
    assert normalize_wb_datetime("") is None


# ── pagination (walk HasNext) ──────────────────────────────

@pytest.mark.asyncio
async def test_list_sent_parcels_walks_all_pages():
    env1 = {"HasNext": True, "Data": [{"Id": "a"}]}
    env2 = {"HasNext": False, "Data": [{"Id": "b"}]}
    get = AsyncMock(side_effect=[_response(env1), _response(env2)])
    cm, client_inner = _async_client_cm(get)

    with patch("services.westernbid.httpx.AsyncClient", return_value=cm), patch(
        "services.westernbid.asyncio.sleep", new=AsyncMock()
    ):
        client = WesternBidClient("api-key", "login", "https://wbdeveloper.systems/")
        items = await client.list_sent_parcels(
            from_date=datetime(2026, 4, 1, tzinfo=timezone.utc)
        )

    assert [i["Id"] for i in items] == ["a", "b"]
    assert client_inner.get.await_count == 2
    # Page number advances on the second request.
    assert client_inner.get.await_args_list[1].kwargs["params"]["PageNr"] == 2


# ── retry on transient HTTP error (429/5xx) ────────────────

@pytest.mark.asyncio
async def test_get_retries_on_httpx_http_error(monkeypatch):
    monkeypatch.setattr(WesternBidClient._get.retry, "wait", wait_none())
    success = _response({"HasNext": False, "Data": []})
    get = AsyncMock(
        side_effect=[httpx.HTTPError("429"), httpx.HTTPError("503"), success]
    )
    cm, client_inner = _async_client_cm(get)

    with patch("services.westernbid.httpx.AsyncClient", return_value=cm):
        client = WesternBidClient("api-key", "login", "https://wbdeveloper.systems")
        result = await client._get("/Shipping/parcels/sent", {"PageNr": 1})

    assert result == {"HasNext": False, "Data": []}
    assert client_inner.get.await_count == 3


# ── credentials never appear in logs (task rule 5) ─────────

@pytest.mark.asyncio
async def test_credentials_never_logged(caplog):
    get = AsyncMock(return_value=_response({"HasNext": False, "Data": [SAMPLE_ITEM]}))
    cm, _ = _async_client_cm(get)

    with patch("services.westernbid.httpx.AsyncClient", return_value=cm), patch(
        "services.westernbid.asyncio.sleep", new=AsyncMock()
    ), caplog.at_level(logging.DEBUG, logger="services.westernbid"):
        client = WesternBidClient("SECRET-API-KEY", "SECRET-LOGIN", "https://x")
        await client.list_sent_parcels(
            from_date=datetime(2026, 4, 1, tzinfo=timezone.utc)
        )

    blob = "\n".join(r.getMessage() for r in caplog.records)
    assert "SECRET-API-KEY" not in blob
    assert "SECRET-LOGIN" not in blob


# ── poller: field mapping + upsert (task rules 4, 8, 10) ───

def test_map_wb_item_keeps_status_raw_and_normalizes_date():
    fields = scheduler._map_wb_item(SAMPLE_ITEM)
    assert fields["wb_status"] == "Parcel created"       # raw text, not enum
    assert fields["payment_status"] == "Paid"            # raw text
    assert fields["tracking_numbers"] == ["1Z999"]
    assert fields["package"] == {"weight": "1.2"}
    assert fields["wb_created_at"].tzinfo == timezone.utc
    assert fields["wb_created_at"].hour == 11             # -05:00 → UTC


def _poll_session(execute_results, get_results):
    """Build a fake async_session_factory() context manager.

    execute_results: sequence returned by db.execute (system-user, then DISTINCT×2).
    get_results:     sequence returned by db.get (per-parcel upsert lookup).
    """
    db = MagicMock()
    db.execute = AsyncMock(side_effect=list(execute_results))
    db.get = AsyncMock(side_effect=list(get_results))
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=db)
    cm.__aexit__ = AsyncMock(return_value=None)
    return cm, db


def _scalar_one(value):
    r = MagicMock()
    r.scalar_one_or_none.return_value = value
    return r


def _distinct(values):
    r = MagicMock()
    r.scalars.return_value.all.return_value = list(values)
    return r


@pytest.mark.asyncio
async def test_poll_inserts_new_parcel_then_updates_on_repoll(monkeypatch):
    """Same parcel twice → one insert, then one update (upsert idempotency)."""
    monkeypatch.setattr(scheduler, "_wb_missing_creds_logged", False)

    client = MagicMock()
    client.list_sent_parcels = AsyncMock(return_value=[SAMPLE_ITEM])

    # ── Run 1: parcel not yet in the mirror → insert.
    cm1, db1 = _poll_session(
        execute_results=[_scalar_one(MagicMock()), _distinct([]), _distinct([])],
        get_results=[None],
    )
    with patch.object(scheduler, "async_session_factory", return_value=cm1), patch.object(
        scheduler, "load_westernbid_credentials", AsyncMock(return_value=("k", "l"))
    ), patch.object(scheduler, "WesternBidClient", return_value=client):
        await scheduler.run_westernbid_poll()

    assert db1.add.call_count == 1
    db1.commit.assert_awaited_once()

    # ── Run 2: parcel already present → update in place, no new row.
    existing = MagicMock()
    cm2, db2 = _poll_session(
        execute_results=[
            _scalar_one(MagicMock()),
            _distinct(["Parcel created"]),
            _distinct(["Paid"]),
        ],
        get_results=[existing],
    )
    with patch.object(scheduler, "async_session_factory", return_value=cm2), patch.object(
        scheduler, "load_westernbid_credentials", AsyncMock(return_value=("k", "l"))
    ), patch.object(scheduler, "WesternBidClient", return_value=client):
        await scheduler.run_westernbid_poll()

    assert db2.add.call_count == 0
    assert existing.wb_status == "Parcel created"
    assert existing.last_seen_at is not None
    db2.commit.assert_awaited_once()


# ── poller: graceful no-op + single log when creds absent (rule 6) ──

@pytest.mark.asyncio
async def test_poll_noop_and_logs_once_when_credentials_absent(monkeypatch, caplog):
    monkeypatch.setattr(scheduler, "_wb_missing_creds_logged", False)
    client_factory = MagicMock()

    def run():
        cm, db = _poll_session(execute_results=[_scalar_one(MagicMock())], get_results=[])
        return cm, db

    with patch.object(
        scheduler, "load_westernbid_credentials", AsyncMock(return_value=None)
    ), patch.object(scheduler, "WesternBidClient", client_factory), caplog.at_level(
        logging.INFO, logger="scheduler"
    ):
        cm1, _ = run()
        with patch.object(scheduler, "async_session_factory", return_value=cm1):
            await scheduler.run_westernbid_poll()
        cm2, _ = run()
        with patch.object(scheduler, "async_session_factory", return_value=cm2):
            await scheduler.run_westernbid_poll()

    # No WB client was ever constructed (true no-op, never reaches WB).
    client_factory.assert_not_called()
    # The "not configured" line is logged exactly once across two polls.
    not_configured = [
        r for r in caplog.records if "credentials not configured" in r.getMessage()
    ]
    assert len(not_configured) == 1


# ── access control (OQ1) ───────────────────────────────────

@pytest.mark.asyncio
async def test_parcel_list_gate_forbids_designer():
    """The parcel list is gated OWNER+MANAGER — a DESIGNER is 403."""
    checker = require_role(UserRole.OWNER, UserRole.MANAGER)
    designer = MagicMock()
    designer.role = UserRole.DESIGNER
    with pytest.raises(HTTPException) as exc:
        await checker(current_user=designer)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_credentials_gate_forbids_manager():
    """WB credentials are OWNER-only — a MANAGER is 403."""
    checker = require_role(UserRole.OWNER)
    manager = MagicMock()
    manager.role = UserRole.MANAGER
    with pytest.raises(HTTPException) as exc:
        await checker(current_user=manager)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_parcel_list_gate_allows_manager_and_owner():
    checker = require_role(UserRole.OWNER, UserRole.MANAGER)
    for role in (UserRole.OWNER, UserRole.MANAGER):
        user = MagicMock()
        user.role = role
        assert await checker(current_user=user) is user


# ── WB-3: label-type resolver (task rule 2) ────────────────

@pytest.mark.parametrize(
    "shipping_type,expected",
    [
        ("NovaPost", ("NpuLabel", "Label10x15")),
        ("UPS", ("Label", "Label10x15")),
        ("ParcelFromFulfillmentCenterWarehouse", ("Label", "Label10x15")),
        ("ConsolidationOptimum", ("Label", "Label10x15")),
        ("ConsolidationPlus", ("Label", "Label10x15")),
        # NovaPoshtaGlobal has no API thermal label → unsupported (rule 6).
        ("NovaPoshtaGlobal", None),
        # Anything unclassified must NOT guess a document.
        ("SomethingNew", None),
        (None, None),
        ("", None),
    ],
)
def test_resolve_label_type(shipping_type, expected):
    assert resolve_label_type(shipping_type) == expected


# ── WB-3: get_document status branching (task rule 7) ──────

def _doc_response(status_code: int, content: bytes = b"%PDF-1.7 ..."):
    r = MagicMock()
    r.status_code = status_code
    r.content = content
    return r


@pytest.mark.asyncio
async def test_get_document_returns_pdf_bytes_on_200():
    get = AsyncMock(return_value=_doc_response(200, b"%PDF-1.7 hello"))
    cm, inner = _async_client_cm(get)
    with patch("services.westernbid.httpx.AsyncClient", return_value=cm):
        client = WesternBidClient("k", "l", "https://system.westernbid.com")
        body = await client.get_document(
            uuid.uuid4(), "NpuLabel", "Label10x15"
        )
    assert body.startswith(b"%PDF")
    assert inner.get.await_count == 1


@pytest.mark.asyncio
async def test_get_document_400_raises_not_ready_and_is_not_retried(monkeypatch):
    monkeypatch.setattr(WesternBidClient.get_document.retry, "wait", wait_none())
    get = AsyncMock(return_value=_doc_response(400, b"{}"))
    cm, inner = _async_client_cm(get)
    with patch("services.westernbid.httpx.AsyncClient", return_value=cm):
        client = WesternBidClient("k", "l", "https://system.westernbid.com")
        with pytest.raises(WesternBidLabelNotReady):
            await client.get_document(uuid.uuid4(), "NpuLabel", "Label10x15")
    # 400 is a definitive answer — never retried.
    assert inner.get.await_count == 1


@pytest.mark.asyncio
async def test_get_document_5xx_is_retried_then_succeeds(monkeypatch):
    monkeypatch.setattr(WesternBidClient.get_document.retry, "wait", wait_none())
    get = AsyncMock(
        side_effect=[
            _doc_response(503, b"err"),
            _doc_response(502, b"err"),
            _doc_response(200, b"%PDF-1.7 ok"),
        ]
    )
    cm, inner = _async_client_cm(get)
    with patch("services.westernbid.httpx.AsyncClient", return_value=cm):
        client = WesternBidClient("k", "l", "https://system.westernbid.com")
        body = await client.get_document(uuid.uuid4(), "Label", "Label10x15")
    assert body.startswith(b"%PDF")
    assert inner.get.await_count == 3


@pytest.mark.asyncio
async def test_get_document_200_non_pdf_is_business_error(monkeypatch):
    monkeypatch.setattr(WesternBidClient.get_document.retry, "wait", wait_none())
    get = AsyncMock(return_value=_doc_response(200, b'{"ErrorCode":1}'))
    cm, inner = _async_client_cm(get)
    with patch("services.westernbid.httpx.AsyncClient", return_value=cm):
        client = WesternBidClient("k", "l", "https://system.westernbid.com")
        with pytest.raises(WesternBidAPIError):
            await client.get_document(uuid.uuid4(), "Label", "Label10x15")
    # A non-PDF 200 is definitive (not transient) → not retried.
    assert inner.get.await_count == 1


# ── WB-3: candidate search + ranking (task rules 3, Q4) ────

@pytest.mark.asyncio
async def test_search_sent_parcels_filters_by_name_and_country():
    get = AsyncMock(return_value=_response({"HasNext": False, "Data": [SAMPLE_ITEM]}))
    cm, inner = _async_client_cm(get)
    with patch("services.westernbid.httpx.AsyncClient", return_value=cm):
        client = WesternBidClient("k", "l", "https://system.westernbid.com")
        items = await client.search_sent_parcels(
            "Gizem Yilmaz", "DE", datetime(2026, 4, 1, tzinfo=timezone.utc)
        )
    assert items == [SAMPLE_ITEM]
    params = inner.get.await_args.kwargs["params"]
    assert params["RecipientName"] == "Gizem Yilmaz"
    assert params["RecipientCountryCode"] == "DE"
    # RecipientPhone is deliberately never sent (proven near-useless, WB-3 Q3).
    assert "RecipientPhone" not in params


@pytest.mark.asyncio
async def test_search_sent_parcels_omits_country_when_none():
    get = AsyncMock(return_value=_response({"HasNext": False, "Data": []}))
    cm, inner = _async_client_cm(get)
    with patch("services.westernbid.httpx.AsyncClient", return_value=cm):
        client = WesternBidClient("k", "l", "https://system.westernbid.com")
        await client.search_sent_parcels(
            "Nobody", None, datetime(2026, 4, 1, tzinfo=timezone.utc)
        )
    assert "RecipientCountryCode" not in inner.get.await_args.kwargs["params"]


def test_rank_candidates_prefers_zip_match_then_date_proximity():
    order_created = datetime(2026, 5, 10, tzinfo=timezone.utc)
    far_zip_match = {
        "Id": "zip", "RecipientPostalCode": "90210",
        "CreatedDate": "2026-01-01T00:00:00",  # far in time…
    }
    near_zip_miss = {
        "Id": "near", "RecipientPostalCode": "99999",
        "CreatedDate": "2026-05-11T00:00:00",  # …but close in time
    }
    far_zip_miss = {
        "Id": "far", "RecipientPostalCode": "99999",
        "CreatedDate": "2026-03-01T00:00:00",
    }
    ranked = rank_candidates(
        [near_zip_miss, far_zip_miss, far_zip_match],
        order_zip="90210",
        order_created_at=order_created,
    )
    # Zip equality wins outright, regardless of date distance.
    assert ranked[0]["Id"] == "zip"
    # Among the zip-misses, the closer CreatedDate ranks higher.
    assert [c["Id"] for c in ranked[1:]] == ["near", "far"]


@pytest.mark.asyncio
async def test_find_candidate_parcels_searches_then_ranks():
    client = MagicMock()
    client.search_sent_parcels = AsyncMock(
        return_value=[
            {"Id": "b", "RecipientPostalCode": "111", "CreatedDate": "2026-05-01T00:00:00"},
            {"Id": "a", "RecipientPostalCode": "222", "CreatedDate": "2026-05-01T00:00:00"},
        ]
    )
    ranked = await find_candidate_parcels(
        client,
        recipient_name="Jane Doe",
        recipient_country_code="US",
        order_zip="222",
        order_created_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        from_date=datetime(2026, 4, 1, tzinfo=timezone.utc),
    )
    client.search_sent_parcels.assert_awaited_once_with(
        "Jane Doe", "US", datetime(2026, 4, 1, tzinfo=timezone.utc)
    )
    assert ranked[0]["Id"] == "a"  # zip match floats to the top
