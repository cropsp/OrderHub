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
    WesternBidClient,
    normalize_wb_datetime,
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
