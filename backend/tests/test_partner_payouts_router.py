"""PART-1 — partner_payouts router regression guards.

Five guards:
  1. require_role(OWNER, MANAGER) raises 403 for DESIGNER.
  2. require_role(OWNER, MANAGER) returns the user for OWNER and MANAGER.
  3. Router list_settlements wires compute_settlement_payment_progress and
     produces a PartnerSettlementListResponse with paid_amount populated.
  4. Router preview_settlement happy-path returns a single-currency response.
  5. Router get_partner_names returns the deduplicated list.
"""

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from models.partner_settlement import PartnerSettlementFormula
from models.user import UserRole
from routers import partner_payouts as router_module
from routers.dependencies import require_role
from schemas.finance import CurrencyAmount
from schemas.partner_payout import PartnerPayoutPreviewRequest


def _make_user(role: UserRole):
    user = MagicMock()
    user.id = uuid.uuid4()
    user.role = role
    return user


@pytest.mark.asyncio
async def test_require_role_blocks_designer():
    checker = require_role(UserRole.OWNER, UserRole.MANAGER)
    with pytest.raises(HTTPException) as exc:
        await checker(current_user=_make_user(UserRole.DESIGNER))
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_require_role_allows_owner_and_manager():
    checker = require_role(UserRole.OWNER, UserRole.MANAGER)
    for role in (UserRole.OWNER, UserRole.MANAGER):
        user = _make_user(role)
        result = await checker(current_user=user)
        assert result is user


@pytest.mark.asyncio
async def test_list_settlements_populates_paid_amount(monkeypatch):
    shop_id = uuid.uuid4()
    settlement_id = uuid.uuid4()

    fake_settlement = MagicMock()
    fake_settlement.id = settlement_id
    fake_settlement.shop_id = shop_id
    fake_settlement.partner_name = "Олег"
    fake_settlement.formula_type = PartnerSettlementFormula.NET_PROFIT_PRODUCT_ONLY
    fake_settlement.percent = Decimal("25.00")
    fake_settlement.period_start = date(2026, 5, 1)
    fake_settlement.period_end = date(2026, 5, 31)
    fake_settlement.base_amount = Decimal("9800.00")
    fake_settlement.base_currency = "UAH"
    fake_settlement.computed_amount = Decimal("2450.00")
    fake_settlement.notes = None
    fake_settlement.created_at = datetime.now(timezone.utc)
    fake_settlement.created_by_user_id = uuid.uuid4()

    async def fake_list(db, sid, partner, limit, offset):
        assert sid == shop_id
        return [fake_settlement], 1

    async def fake_progress(db, ids):
        return {settlement_id: Decimal("1000.00")}

    monkeypatch.setattr(
        router_module.partner_payout_service, "list_settlements", fake_list
    )
    monkeypatch.setattr(
        router_module.partner_payout_service,
        "compute_settlement_payment_progress",
        fake_progress,
    )

    response = await router_module.list_settlements(
        shop_id=shop_id, partner=None, limit=50, offset=0, db=MagicMock()
    )
    assert response.total == 1
    assert len(response.items) == 1
    assert response.items[0].paid_amount == Decimal("1000.00")
    assert response.items[0].computed_amount == Decimal("2450.00")


@pytest.mark.asyncio
async def test_preview_settlement_single_currency(monkeypatch):
    async def fake_preview(db, shop_id, payload):
        from schemas.partner_payout import PartnerPayoutPreviewResponse
        return PartnerPayoutPreviewResponse(
            base_amount=Decimal("9800.00"),
            base_currency="UAH",
            computed_amount=Decimal("2450.00"),
        )

    monkeypatch.setattr(
        router_module.partner_payout_service, "preview_settlement", fake_preview
    )
    payload = PartnerPayoutPreviewRequest(
        formula_type="net_profit_product_only",
        percent=Decimal("25"),
        period_start=date(2026, 5, 1),
        period_end=date(2026, 5, 31),
    )
    response = await router_module.preview_settlement(
        shop_id=uuid.uuid4(), payload=payload, db=MagicMock()
    )
    assert response.computed_amount == Decimal("2450.00")
    assert response.base_currency == "UAH"


@pytest.mark.asyncio
async def test_get_partner_names_returns_deduplicated_list(monkeypatch):
    async def fake_names(db, shop_id):
        return ["Андрій", "Олег", "Світлана"]

    monkeypatch.setattr(
        router_module.partner_payout_service, "list_partner_names", fake_names
    )
    response = await router_module.get_partner_names(
        shop_id=uuid.uuid4(), db=MagicMock()
    )
    assert response.items == ["Андрій", "Олег", "Світлана"]
