"""USER-ACCESS-2 — capability resolution, guards, censoring, audit symmetry.

Mock-based, matching test_shop_access.py: services/guards awaited directly with
AsyncMock dbs. Covers the CapabilitySet value object, get_capabilities
(owner short-circuit / role default / explicit override), the assert_capability
guard, the shared order-financial censor (LEAK 1/2), the finance card strip, and
the revoke-source/audit symmetry.
"""
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock

import pytest

from models.user import Capability, UserRole
from services.access_service import (
    CapabilitySet,
    get_capabilities,
    set_capabilities,
    revoke_shop_access,
    grant_shop_access,
)
from services.order_service import censor_order_financials, ORDER_COST_FIELDS
from routers.dependencies import assert_capability
from fastapi import HTTPException


# ── helpers ────────────────────────────────────────────────

def _user(role, uid=None):
    u = MagicMock()
    u.role = role
    u.id = uid or uuid4()
    return u


def _rows(rows):
    r = MagicMock()
    r.all.return_value = rows
    return r


def _rowcount(n):
    r = MagicMock()
    r.rowcount = n
    return r


def _db():
    """AsyncMock session whose .add is synchronous (matches SQLAlchemy)."""
    db = AsyncMock()
    db.add = MagicMock()
    return db


# ── CapabilitySet ──────────────────────────────────────────

def test_capabilityset_owner_has_everything():
    owner = CapabilitySet.owner()
    assert owner.has(Capability.VIEW_FINANCE) is True
    assert owner.has(Capability.VIEW_COSTS) is True


def test_capabilityset_empty_has_nothing():
    empty = CapabilitySet()
    assert empty.has(Capability.VIEW_FINANCE) is False
    assert empty.has(Capability.VIEW_COSTS) is False


def test_capabilityset_partial():
    cs = CapabilitySet(granted=frozenset({Capability.VIEW_FINANCE}))
    assert cs.has(Capability.VIEW_FINANCE) is True
    assert cs.has(Capability.VIEW_COSTS) is False


# ── get_capabilities ───────────────────────────────────────

@pytest.mark.asyncio
async def test_owner_short_circuits_without_query():
    db = AsyncMock()
    caps = await get_capabilities(db, _user(UserRole.OWNER))
    assert caps.is_owner is True
    assert caps.has(Capability.VIEW_COSTS) is True
    db.execute.assert_not_called()  # no DB hit for owner


@pytest.mark.asyncio
async def test_manager_role_default_is_deny():
    db = AsyncMock()
    db.execute.return_value = _rows([])  # no explicit rows
    caps = await get_capabilities(db, _user(UserRole.MANAGER))
    assert caps.has(Capability.VIEW_FINANCE) is False
    assert caps.has(Capability.VIEW_COSTS) is False


@pytest.mark.asyncio
async def test_explicit_grant_overrides_default():
    db = AsyncMock()
    db.execute.return_value = _rows([("view_finance", True)])
    caps = await get_capabilities(db, _user(UserRole.MANAGER))
    assert caps.has(Capability.VIEW_FINANCE) is True
    assert caps.has(Capability.VIEW_COSTS) is False


@pytest.mark.asyncio
async def test_explicit_false_row_denies():
    db = AsyncMock()
    db.execute.return_value = _rows([("view_finance", False), ("view_costs", True)])
    caps = await get_capabilities(db, _user(UserRole.MANAGER))
    assert caps.has(Capability.VIEW_FINANCE) is False
    assert caps.has(Capability.VIEW_COSTS) is True


@pytest.mark.asyncio
async def test_unknown_capability_name_ignored():
    db = AsyncMock()
    db.execute.return_value = _rows([("view_finance", True), ("legacy_cap", True)])
    caps = await get_capabilities(db, _user(UserRole.MANAGER))
    assert caps.has(Capability.VIEW_FINANCE) is True


@pytest.mark.asyncio
async def test_designer_default_deny():
    db = AsyncMock()
    db.execute.return_value = _rows([])
    caps = await get_capabilities(db, _user(UserRole.DESIGNER))
    assert caps.has(Capability.VIEW_FINANCE) is False
    assert caps.has(Capability.VIEW_COSTS) is False


# ── assert_capability guard ────────────────────────────────

@pytest.mark.asyncio
async def test_assert_capability_denies_without():
    db = AsyncMock()
    db.execute.return_value = _rows([])
    with pytest.raises(HTTPException) as exc:
        await assert_capability(db, Capability.VIEW_FINANCE, _user(UserRole.MANAGER))
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_assert_capability_passes_owner():
    db = AsyncMock()
    await assert_capability(db, Capability.VIEW_COSTS, _user(UserRole.OWNER))
    db.execute.assert_not_called()


# ── shared order-financial censor (LEAK 1 / LEAK 2) ────────

def _order_dict():
    d = {f: 123.45 for f in ORDER_COST_FIELDS}
    d["total_price"] = 500.0
    d["status_history"] = [
        {"comment": "Fields updated: production_cost: 1 -> 2, title: a -> b"}
    ]
    return d


def test_censor_nulls_all_cost_fields_when_denied():
    data = censor_order_financials(_order_dict(), can_view_costs=False)
    for f in ORDER_COST_FIELDS:
        assert data[f] is None
    # revenue field untouched
    assert data["total_price"] == 500.0


def test_censor_redacts_history_comment_when_denied():
    data = censor_order_financials(_order_dict(), can_view_costs=False)
    comment = data["status_history"][0]["comment"]
    assert "[redacted]" in comment
    assert "title: a -> b" in comment  # non-financial change preserved


def test_censor_passthrough_when_allowed():
    data = censor_order_financials(_order_dict(), can_view_costs=True)
    for f in ORDER_COST_FIELDS:
        assert data[f] == 123.45


def test_censor_computed_production_cost_included():
    # LEAK 2 regression: computed_production_cost must be in the censor set.
    assert "computed_production_cost" in ORDER_COST_FIELDS
    data = censor_order_financials(_order_dict(), can_view_costs=False)
    assert data["computed_production_cost"] is None


def test_censor_list_row_without_history_is_safe():
    # list rows have no status_history key — must not raise.
    row = {f: 1.0 for f in ORDER_COST_FIELDS}
    out = censor_order_financials(row, can_view_costs=False)
    assert all(out[f] is None for f in ORDER_COST_FIELDS)


# ── finance itemised-cost strip ────────────────────────────

def test_finance_strip_blanks_cost_cards_keeps_margin():
    from routers.finance import _strip_itemised_costs
    from schemas.finance import (
        ShopFinanceResponse, KpiCard, CurrencyAmount, OrderCountCard,
        DiagnosticInfo,
    )

    def card(v):
        return KpiCard(
            current=[CurrencyAmount(currency="USD", amount=v)],
            previous=[], change_percent=None,
        )

    resp = ShopFinanceResponse(
        shop_id="s", shop_name="S", period_start_iso="", period_end_iso="",
        granularity="day",
        revenue=card(1000), cogs=card(400), fees=card(50),
        allocated_overhead_expenses=card(20), refunds=card(30), net_profit=card(500),
        pipeline_value=card(0),
        order_count=OrderCountCard(current=1, previous=0, change_percent=None),
        aov=card(1000), time_series=[],
        diagnostic=DiagnosticInfo(
            orders_missing_cost=0, total_orders_in_period=1,
            orders_with_computed_cost=1,
        ),
        shipping_net=card(10),
    )
    stripped = _strip_itemised_costs(resp)
    # itemised cost cards blanked
    assert stripped.cogs.current == []
    assert stripped.allocated_overhead_expenses.current == []
    assert stripped.fees.current == []
    assert stripped.shipping_net.current == []
    # revenue + margin preserved
    assert stripped.revenue.current[0].amount == 1000
    assert stripped.net_profit.current[0].amount == 500
    # SHOPIFY-REFUNDS: refunds are a revenue-side deduction (view_finance), NOT an
    # itemised cost — they stay visible when view_costs is absent.
    assert stripped.refunds.current[0].amount == 30


# ── grant/revoke audit + source symmetry ───────────────────

@pytest.mark.asyncio
async def test_revoke_accepts_source_and_audits_on_change():
    db = _db()
    db.execute.return_value = _rowcount(1)  # a row was removed
    uid, sid, actor = uuid4(), uuid4(), uuid4()
    await revoke_shop_access(db, uid, sid, actor_id=actor, source="editor")
    # one execute for the delete; audit row added via db.add
    assert db.add.called


@pytest.mark.asyncio
async def test_revoke_noop_does_not_audit():
    db = _db()
    db.execute.return_value = _rowcount(0)  # nothing removed
    await revoke_shop_access(db, uuid4(), uuid4(), actor_id=uuid4())
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_grant_audits_only_on_real_insert():
    db = _db()
    db.execute.return_value = _rowcount(0)  # idempotent no-op (already granted)
    await grant_shop_access(db, uuid4(), uuid4(), actor_id=uuid4(), source="assignment")
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_set_capabilities_writes_and_audits():
    db = _db()
    uid, actor = uuid4(), uuid4()
    await set_capabilities(
        db, uid, {Capability.VIEW_FINANCE: True, Capability.VIEW_COSTS: False},
        actor_id=actor,
    )
    # two upserts executed, two audit rows added
    assert db.execute.await_count == 2
    assert db.add.call_count == 2
