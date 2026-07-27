"""SHOPIFY-REFUNDS — refund capture service (sync_shop_refunds) guards.

Model 2: a Shopify refund is booked as a separate, dated event keyed by
`shopify_refund_id`, dated by its own `createdAt` (`refunded_at`). These tests use
the codebase's mocked-AsyncSession style — no real DB — and monkeypatch the paged
fetch so we exercise the upsert/idempotency/tally logic deterministically.
"""
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql.dml import Insert as PGInsert

import services.shopify_sync as shopify_sync
from models.shop import ShopPlatform
from services.shopify_sync import sync_shop_refunds


def _shop():
    shop = MagicMock()
    shop.id = uuid.uuid4()
    shop.name = "Lamamarka"
    shop.platform = ShopPlatform.SHOPIFY
    shop.shopify_store_url = "test.myshopify.com"
    shop.shopify_access_token_encrypted = "enc"
    return shop


def _refund(rid="999", created="2026-07-15T10:00:00Z", amount="29.99", currency="USD"):
    return {
        "id": f"gid://shopify/Refund/{rid}",
        "createdAt": created,
        "totalRefundedSet": {"shopMoney": {"amount": amount, "currencyCode": currency}},
    }


def _page(refunds, order_gid="gid://shopify/Order/123"):
    return {
        "data": {"orders": {
            "pageInfo": {"hasNextPage": False, "endCursor": None},
            "edges": [{"node": {"id": order_gid, "refunds": refunds}}],
        }},
        "extensions": {},
    }


def _make_db(existing_ids, order_uuid):
    """Mock AsyncSession dispatching by statement kind:
    existing-refund-ids select, order-id resolve, and the ON CONFLICT insert."""
    captured = {"inserts": [], "all": []}

    async def fake_execute(stmt):
        captured["all"].append(stmt)
        r = MagicMock()
        if isinstance(stmt, PGInsert):
            captured["inserts"].append(stmt)
            r.rowcount = 1
            return r
        s = str(stmt).lower()
        if "order_refunds.shopify_refund_id" in s:
            scal = MagicMock()
            scal.all.return_value = list(existing_ids)
            r.scalars.return_value = scal
            return r
        if "orders.external_id" in s:
            r.scalar_one_or_none.return_value = order_uuid
            return r
        r.scalar_one_or_none.return_value = None
        return r

    db = MagicMock()
    db.execute = AsyncMock(side_effect=fake_execute)
    db.flush = AsyncMock()
    return db, captured


def _patch_fetch(monkeypatch, page):
    async def fake_fetch(shop_url, token, variables, query=None):
        return page
    monkeypatch.setattr(shopify_sync, "_fetch_orders_page", fake_fetch)
    monkeypatch.setattr(shopify_sync, "decrypt_value", lambda _enc: "token")


@pytest.mark.asyncio
async def test_refund_inserts_and_is_idempotent(monkeypatch):
    """First run inserts the refund via an ON CONFLICT DO NOTHING upsert; a second run
    where the id is already stored inserts nothing (dedup on shopify_refund_id)."""
    order_uuid = uuid.uuid4()

    # Run 1: nothing stored yet → one insert.
    _patch_fetch(monkeypatch, _page([_refund(rid="999")]))
    db, captured = _make_db(existing_ids=set(), order_uuid=order_uuid)
    res = await sync_shop_refunds(db, _shop(), updated_since=None)
    assert res["refunds_found"] == 1
    assert res["inserted"] == 1
    assert res["already_present"] == 0
    assert len(captured["inserts"]) == 1
    # Idempotency is guaranteed at the DB by ON CONFLICT DO NOTHING.
    insert_sql = str(
        captured["inserts"][0].compile(dialect=postgresql.dialect())
    ).lower()
    assert "on conflict on constraint uq_order_refund_shopify_id do nothing" in insert_sql

    # Run 2: id already stored → skipped, zero inserts.
    _patch_fetch(monkeypatch, _page([_refund(rid="999")]))
    db2, captured2 = _make_db(existing_ids={"999"}, order_uuid=order_uuid)
    res2 = await sync_shop_refunds(db2, _shop(), updated_since=None)
    assert res2["refunds_found"] == 1
    assert res2["inserted"] == 0
    assert res2["already_present"] == 1
    assert captured2["inserts"] == []


@pytest.mark.asyncio
async def test_refund_dry_run_writes_nothing(monkeypatch):
    """dry_run reports the tally (found + would-create) without issuing any insert."""
    _patch_fetch(monkeypatch, _page([_refund(rid="999")]))
    db, captured = _make_db(existing_ids=set(), order_uuid=uuid.uuid4())

    res = await sync_shop_refunds(db, _shop(), updated_since=None, dry_run=True)

    assert res["dry_run"] is True
    assert res["refunds_found"] == 1
    assert res["inserted"] == 0
    assert captured["inserts"] == []
    # would-create is tallied in the per-month bucket for the reconciliation report.
    assert res["by_month"]["2026-07"]["created"] == 1


@pytest.mark.asyncio
async def test_refund_dated_by_own_created_at(monkeypatch):
    """Model 2: the refund lands in the month of its OWN createdAt (July), regardless
    of when the order was placed, and its amount sums per currency."""
    _patch_fetch(monkeypatch, _page([_refund(rid="999", created="2026-07-15T10:00:00Z")]))
    db, _ = _make_db(existing_ids=set(), order_uuid=uuid.uuid4())

    res = await sync_shop_refunds(db, _shop(), updated_since=None)

    assert "2026-07" in res["by_month"]
    assert res["by_month"]["2026-07"]["found"] == 1
    assert res["amount_by_currency"] == {"USD": 29.99}


@pytest.mark.asyncio
async def test_refund_zero_amount_skipped(monkeypatch):
    """A $0 refund (restock-only, no money moved) is not counted or stored."""
    _patch_fetch(monkeypatch, _page([_refund(rid="999", amount="0.00")]))
    db, captured = _make_db(existing_ids=set(), order_uuid=uuid.uuid4())

    res = await sync_shop_refunds(db, _shop(), updated_since=None)

    assert res["refunds_found"] == 0
    assert res["inserted"] == 0
    assert captured["inserts"] == []


@pytest.mark.asyncio
async def test_refund_on_unimported_order_skipped(monkeypatch):
    """A refund on an order we never imported has nothing to attach to — counted as
    skipped_no_order, never inserted."""
    _patch_fetch(monkeypatch, _page([_refund(rid="999")]))
    db, captured = _make_db(existing_ids=set(), order_uuid=None)  # order not found

    res = await sync_shop_refunds(db, _shop(), updated_since=None)

    assert res["refunds_found"] == 1
    assert res["skipped_no_order"] == 1
    assert res["inserted"] == 0
    assert captured["inserts"] == []


@pytest.mark.asyncio
async def test_non_shopify_shop_is_noop(monkeypatch):
    """Non-Shopify shops never hit Shopify — a plain zeroed no-op."""
    called = {"fetch": False}

    async def boom(*a, **k):
        called["fetch"] = True
        raise AssertionError("must not fetch for a non-Shopify shop")

    monkeypatch.setattr(shopify_sync, "_fetch_orders_page", boom)
    shop = _shop()
    shop.platform = ShopPlatform.ETSY
    db, captured = _make_db(existing_ids=set(), order_uuid=None)

    res = await sync_shop_refunds(db, shop, updated_since=None)

    assert res["inserted"] == 0
    assert res["refunds_found"] == 0
    assert called["fetch"] is False


def test_build_refund_query_filter():
    """updated_since builds an `updated_at:>=…` window; None → no filter (full walk)."""
    from datetime import datetime, timezone

    assert shopify_sync._build_refund_query_filter(None) is None
    since = datetime(2026, 7, 1, tzinfo=timezone.utc)
    assert shopify_sync._build_refund_query_filter(since) == "updated_at:>=2026-07-01T00:00:00+00:00"


def test_refund_backfill_request_schema():
    """The retro-fix payload takes only `dry_run` (defaulting True) and must not
    inherit SHOPIFY-BACKFILL's since/until range validator — it walks every order."""
    from schemas.shop import ShopRefundBackfillRequest

    assert ShopRefundBackfillRequest().dry_run is True
    assert ShopRefundBackfillRequest(dry_run=False).dry_run is False


def test_shop_backfill_request_range_validator_intact():
    """Regression: ShopBackfillRequest keeps its own `until >= since` check.

    The refund payload class was once inserted above this validator, silently
    re-parenting it onto the refund schema (500 on every refund backfill, and
    SHOPIFY-BACKFILL accepting an inverted range).
    """
    from datetime import date

    from pydantic import ValidationError

    from schemas.shop import ShopBackfillRequest

    ok = ShopBackfillRequest(since=date(2026, 1, 1), until=date(2026, 2, 1))
    assert ok.dry_run is True
    assert ShopBackfillRequest(since=date(2026, 1, 1)).until is None
    with pytest.raises(ValidationError):
        ShopBackfillRequest(since=date(2026, 2, 1), until=date(2026, 1, 1))
