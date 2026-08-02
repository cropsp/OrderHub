"""FX-CONVERSION — the SHIPPED wiring in order_service.change_order_status.

Two properties that the consumption service cannot guarantee on its own, because
they live in the caller:

  1. The rate is resolved ONCE at the transaction boundary and handed down, so the
     consumption fold issues no settings query and preview/booking can be driven
     with one identical rate.
  2. computed_production_cost and its three provenance columns move TOGETHER, and
     only on a non-idempotent run. Writing the rate outside that guard would stamp
     today's rate onto a cost booked months ago on any
     SHIPPED -> IN_PROGRESS -> SHIPPED round trip, and the resulting (cost, rate)
     pair would read as data rather than as a bug.

Property 2 is what makes "history is frozen" true: the sprint is forward-only, so
a snapshot that silently moves can never be reconciled against anything.
"""
import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models.order import OrderStatus
from models.user import UserRole
from services.fx_service import FxRates
from services.order_consumption_service import ConsumptionResult
from services.order_service import change_order_status


def _order(status=OrderStatus.IN_PRODUCTION, currency="USD"):
    order = MagicMock()
    order.id = uuid.uuid4()
    order.shop_id = uuid.uuid4()
    order.status = status
    order.currency = currency
    order.shipped_at = None
    order.completed_at = None
    order.assigned_designer_id = uuid.uuid4()
    order.computed_production_cost = None
    order.cogs_fx_rate = None
    order.cogs_basis_amount = None
    order.cogs_basis_currency = None
    return order


def _user(role=UserRole.OWNER):
    user = MagicMock()
    user.id = uuid.uuid4()
    user.role = role
    return user


def _db():
    db = MagicMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.execute = AsyncMock()
    return db


BOOKED = ConsumptionResult(
    computed_production_cost=Decimal("12.05"),
    fx_rate_used=Decimal("41.5"),
    basis_amount=Decimal("500.0000"),
    basis_currency="UAH",
)


@pytest.mark.asyncio
async def test_shipping_stamps_the_cost_and_its_provenance_together():
    order, user, db = _order(), _user(), _db()

    with patch(
        "services.fx_service.resolve",
        AsyncMock(return_value=FxRates(uah_per_usd=Decimal("41.5"), source="manual")),
    ), patch(
        "services.order_consumption_service.consume_materials_for_order",
        AsyncMock(return_value=BOOKED),
    ):
        await change_order_status(db, order, OrderStatus.SHIPPED, user)

    assert order.computed_production_cost == Decimal("12.05")
    assert order.cogs_fx_rate == Decimal("41.5")
    assert order.cogs_basis_amount == Decimal("500.0000")
    assert order.cogs_basis_currency == "UAH"


@pytest.mark.asyncio
async def test_the_resolved_rate_is_passed_down_not_re_read():
    """The consumption fold must not query settings itself — that path runs inside
    the SHIPPED transaction, between the NP TTN write and the commit."""
    order, user, db = _order(), _user(), _db()
    fx = FxRates(uah_per_usd=Decimal("41.5"), source="manual")
    consume = AsyncMock(return_value=BOOKED)

    with patch("services.fx_service.resolve", AsyncMock(return_value=fx)), patch(
        "services.order_consumption_service.consume_materials_for_order", consume
    ):
        await change_order_status(db, order, OrderStatus.SHIPPED, user)

    assert consume.await_args.kwargs["fx"] is fx


@pytest.mark.asyncio
async def test_a_repeat_ship_leaves_every_snapshot_field_untouched():
    """The idempotent path must not move ANY of the four. A rate change between
    the two ships is the case that would corrupt the audit pair."""
    order, user, db = _order(), _user(), _db()

    with patch(
        "services.fx_service.resolve",
        AsyncMock(return_value=FxRates(uah_per_usd=Decimal("41.5"), source="manual")),
    ), patch(
        "services.order_consumption_service.consume_materials_for_order",
        AsyncMock(return_value=BOOKED),
    ):
        await change_order_status(db, order, OrderStatus.SHIPPED, user)

    frozen = (
        order.computed_production_cost,
        order.cogs_fx_rate,
        order.cogs_basis_amount,
        order.cogs_basis_currency,
    )

    # Back to production, then shipped again — at a very different rate.
    order.status = OrderStatus.IN_PRODUCTION
    with patch(
        "services.fx_service.resolve",
        AsyncMock(return_value=FxRates(uah_per_usd=Decimal("99.9"), source="manual")),
    ), patch(
        "services.order_consumption_service.consume_materials_for_order",
        AsyncMock(return_value=ConsumptionResult(idempotent_skip=True)),
    ):
        await change_order_status(db, order, OrderStatus.SHIPPED, user)

    assert (
        order.computed_production_cost,
        order.cogs_fx_rate,
        order.cogs_basis_amount,
        order.cogs_basis_currency,
    ) == frozen


@pytest.mark.asyncio
async def test_a_degraded_booking_clears_the_provenance_too():
    """No cost means no rate and no basis — never a rate stranded beside a NULL
    cost, which would read as 'converted' when nothing was."""
    order, user, db = _order(), _user(), _db()

    with patch(
        "services.fx_service.resolve", AsyncMock(return_value=FxRates.unavailable())
    ), patch(
        "services.order_consumption_service.consume_materials_for_order",
        AsyncMock(
            return_value=ConsumptionResult(
                computed_production_cost=None, warnings=["⚠ no rate"]
            )
        ),
    ):
        _order_out, warnings = await change_order_status(
            db, order, OrderStatus.SHIPPED, user
        )

    assert order.computed_production_cost is None
    assert order.cogs_fx_rate is None
    assert order.cogs_basis_amount is None
    assert order.cogs_basis_currency is None
    assert warnings == ["⚠ no rate"]


@pytest.mark.asyncio
async def test_non_shipped_transitions_do_not_touch_the_snapshot():
    order, user, db = _order(status=OrderStatus.DESIGN_READY), _user(), _db()
    order.computed_production_cost = Decimal("7.00")
    order.cogs_fx_rate = Decimal("41.5")

    with patch("services.fx_service.resolve", AsyncMock()) as resolve:
        await change_order_status(db, order, OrderStatus.IN_PRODUCTION, user)

    resolve.assert_not_awaited()
    assert order.computed_production_cost == Decimal("7.00")
    assert order.cogs_fx_rate == Decimal("41.5")
