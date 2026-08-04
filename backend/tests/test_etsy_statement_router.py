"""STATEMENT-IMPORT — the /imports surface for the statement upload.

One thing under test that no service test can prove: the endpoint commits a real
import and does NOT commit a rehearsal. The service rolls a dry run back itself
(that is where the guarantee lives); this is the surface half of the same
contract, and the reason a forgotten `dry_run` flag cannot write money.

Router functions are awaited directly with mock sessions, matching the style in
test_shop_fee_router.py — the role and capability dependencies are declarative
and are covered by test_route_scope_completeness / test_money_field_completeness.
"""

import inspect
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from models.shop import Shop, ShopPlatform
from routers.imports import import_etsy_statement
from services.etsy_statement_parser import StatementParseError


def _shop():
    return Shop(id=uuid.uuid4(), name="LeatherCraft UA", platform=ShopPlatform.ETSY)


def _upload(name="etsy_statement_2026_4.csv"):
    file = MagicMock()
    file.filename = name
    file.read = AsyncMock(return_value=b"Date,Type\n")
    return file


def _db():
    db = MagicMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    return db


def _user():
    user = MagicMock()
    user.id = uuid.uuid4()
    return user


async def _call(db, *, dry_run, report=None, raises=None):
    shop = _shop()
    with patch("routers.imports._get_etsy_shop", AsyncMock(return_value=shop)), patch(
        "routers.imports.import_statement",
        AsyncMock(return_value=report, side_effect=raises),
    ) as service:
        result = await import_etsy_statement(
            shop_id=shop.id,
            file=_upload(),
            dry_run=dry_run,
            current_user=_user(),
            db=db,
        )
    return result, service


@pytest.mark.asyncio
async def test_a_dry_run_is_never_committed():
    db = _db()
    report = MagicMock(dry_run=True)

    result, service = await _call(db, dry_run=True, report=report)

    assert result is report
    assert service.await_args.kwargs["dry_run"] is True
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_real_import_is_committed():
    db = _db()
    report = MagicMock(dry_run=False)

    result, service = await _call(db, dry_run=False, report=report)

    assert result is report
    assert service.await_args.kwargs["dry_run"] is False
    db.commit.assert_awaited_once()


def test_the_endpoint_defaults_to_a_dry_run():
    """SHOP-FEE-1's rule, at the HTTP surface: booking money is an explicit
    `dry_run=false`, never something a caller falls into by omission."""
    default = inspect.signature(import_etsy_statement).parameters["dry_run"].default
    assert default.default is True


@pytest.mark.asyncio
async def test_a_rejected_row_rolls_back_and_answers_400():
    db = _db()

    with pytest.raises(HTTPException) as exc:
        await _call(db, dry_run=False, raises=StatementParseError("row 7: unknown Type"))

    assert exc.value.status_code == 400
    assert "row 7" in exc.value.detail, "the offending row is the operator's fix"
    db.rollback.assert_awaited_once()
    db.commit.assert_not_awaited()
