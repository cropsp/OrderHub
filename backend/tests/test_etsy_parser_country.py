"""ETSY-COUNTRY-FIX — Etsy CSV parser resolves Ship Country to a real ISO code.

Covers the write path at services.etsy_parser: the "Ship Country" full name is
resolved to ISO alpha-2 and threaded to BOTH the order (shipping_country) and the
customer (via upsert_customer).
"""
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from models.order import Order
from services.etsy_parser import parse_etsy_csv


def _make_shop():
    shop = MagicMock()
    shop.id = uuid4()
    return shop


def _make_db():
    db = MagicMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    no_existing = MagicMock()
    no_existing.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=no_existing)
    return db


def _csv_bytes(ship_country: str) -> bytes:
    header = (
        "Sale ID,Sale Date,Buyer,Buyer Email,Item Name,SKU,Listing ID,Variations,"
        "Quantity,Price,Order Total,Currency,Ship Country,Ship Name,Ship Address1,"
        "Ship City,Ship State,Ship Zipcode\n"
    )
    row = (
        f"S-1,2026-01-15,Alice,a@example.com,Wallet,SKU-1,L-100,,"
        f"1,30,30,USD,{ship_country},Alice,1 St,Gaithersburg,MD,20878\n"
    )
    return (header + row).encode("utf-8")


async def _run(csv_bytes):
    """Parse one CSV, returning (ImportResult, Order, country_passed_to_customer)."""
    shop = _make_shop()
    db = _make_db()
    customer = MagicMock()
    customer.id = uuid4()
    upsert = AsyncMock(return_value=customer)

    fake_svc = MagicMock()
    fake_svc.find_product_by_external_ref = AsyncMock(return_value=None)
    fake_svc.is_sku_taken = AsyncMock(return_value=False)

    with patch("services.etsy_parser.upsert_customer", upsert), \
         patch("services.etsy_parser.CatalogService", return_value=fake_svc):
        result = await parse_etsy_csv(db, shop, csv_bytes, user_id=uuid4())

    orders = [c.args[0] for c in db.add.call_args_list if isinstance(c.args[0], Order)]
    customer_country = upsert.await_args.args[3] if upsert.await_args else None
    return result, orders[0] if orders else None, customer_country


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "ship_country, expected",
    [
        ("United States", "US"),
        ("United Kingdom", "GB"),
        ("Germany", "DE"),
        ("Czech Republic", "CZ"),
        ("Canada", "CA"),
        ("US", "US"),  # already a code — passes through
    ],
)
async def test_ship_country_name_is_resolved_to_iso_code(ship_country, expected):
    result, order, customer_country = await _run(_csv_bytes(ship_country))

    assert result.imported == 1
    assert order.shipping_country == expected
    # The same resolved value must reach the customer — one fix, both write paths.
    assert customer_country == expected


@pytest.mark.asyncio
async def test_full_name_is_not_truncated_to_two_chars():
    """Regression: "United States"[:2] == "Un" rendered as "United Nations"."""
    _, order, customer_country = await _run(_csv_bytes("United States"))
    assert order.shipping_country == "US"
    assert customer_country == "US"


@pytest.mark.asyncio
async def test_unresolvable_country_stores_null_and_still_imports(caplog):
    """Unresolvable → NULL + warning. The columns are VARCHAR(2), so storing the
    raw name would raise and fail the whole order import."""
    with caplog.at_level("WARNING"):
        result, order, customer_country = await _run(_csv_bytes("Elbonia"))

    assert result.imported == 1  # the order is not lost
    assert order.shipping_country is None
    assert customer_country is None
    assert "Elbonia" in caplog.text  # the raw value stays visible


@pytest.mark.asyncio
async def test_missing_ship_country_stores_null_not_fabricated_us():
    header = (
        "Sale ID,Sale Date,Buyer,Buyer Email,Item Name,SKU,Listing ID,Variations,"
        "Quantity,Price,Order Total,Currency,Ship Name,Ship Address1,Ship City\n"
    )
    row = "S-1,2026-01-15,Alice,a@example.com,Wallet,SKU-1,L-100,,1,30,30,USD,Alice,1 St,NYC\n"

    result, order, customer_country = await _run((header + row).encode("utf-8"))

    assert result.imported == 1
    assert order.shipping_country is None
    assert customer_country is None
