"""IMP-1 + BUG-5 — Etsy CSV importer auto-creates Products / ProductVariants.

Covers the catalog auto-create path in services.etsy_parser:
- effective SKU generation (content-keyed by normalized Variations)
- _ensure_catalog_row decision matrix (lazy Product insert, shop-wide SKU dedup,
  in-import idempotency, missing Listing ID handling)
- parse_etsy_csv counter threading and default dimension sentinel.
"""
import re
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from models.product import Product, ProductVariant
from services.etsy_parser import (
    _compute_effective_sku,
    _ensure_catalog_row,
    parse_etsy_csv,
)


HASHED_SKU_RE = re.compile(r"^etsy-[A-Za-z0-9_-]+-[0-9a-f]{8}$")


def _make_shop():
    shop = MagicMock()
    shop.id = uuid4()
    return shop


def _make_db():
    db = MagicMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.execute = AsyncMock()
    return db


def _make_catalog_service(*, existing_product=None, taken_skus=None):
    taken_skus = set(taken_skus or [])
    svc = MagicMock()
    svc.find_product_by_external_ref = AsyncMock(return_value=existing_product)
    svc.is_sku_taken = AsyncMock(side_effect=lambda shop_id, sku: sku in taken_skus)
    return svc


# ---------- _compute_effective_sku ----------


def test_effective_sku_explicit_passes_through():
    assert _compute_effective_sku("123", "  CUSTOM-SKU  ", None) == "CUSTOM-SKU"
    assert _compute_effective_sku("123", "  CUSTOM-SKU  ", "Color: Red") == "CUSTOM-SKU"


def test_effective_sku_empty_variations_no_suffix():
    assert _compute_effective_sku("123", "", None) == "etsy-123"
    assert _compute_effective_sku("123", None, None) == "etsy-123"
    assert _compute_effective_sku("123", "   ", "") == "etsy-123"
    assert _compute_effective_sku("123", "", "   ") == "etsy-123"


def test_effective_sku_same_variations_same_sku():
    sku1 = _compute_effective_sku("L", "", "Color:Red,Size:M")
    sku2 = _compute_effective_sku("L", "", "Color:Red,Size:M")
    assert sku1 == sku2
    assert re.match(r"^etsy-L-[0-9a-f]{8}$", sku1)


def test_effective_sku_normalizes_whitespace():
    sku1 = _compute_effective_sku("L", "", "Color:Red, Pakning:Single")
    sku2 = _compute_effective_sku("L", "", "Color:Red,Pakning:Single")
    sku3 = _compute_effective_sku("L", "", "  Color:Red,Pakning:Single  ")
    assert sku1 == sku2 == sku3


def test_effective_sku_normalizes_case():
    sku1 = _compute_effective_sku("L", "", "Color:Red")
    sku2 = _compute_effective_sku("L", "", "color:red")
    sku3 = _compute_effective_sku("L", "", "COLOR:RED")
    assert sku1 == sku2 == sku3


def test_effective_sku_distinct_variations_distinct_skus():
    sku_red = _compute_effective_sku("L", "", "Color:Red")
    sku_blue = _compute_effective_sku("L", "", "Color:Blue")
    assert sku_red != sku_blue
    assert re.match(r"^etsy-L-[0-9a-f]{8}$", sku_red)
    assert re.match(r"^etsy-L-[0-9a-f]{8}$", sku_blue)


def test_effective_sku_idempotent_across_imports():
    """Hash determinism: same inputs always produce same output across import runs."""
    sku1 = _compute_effective_sku("L", "", "Color:Red")
    sku2 = _compute_effective_sku("L", "", "Color:Red")
    assert sku1 == sku2


# ---------- _ensure_catalog_row ----------


@pytest.mark.asyncio
async def test_ensure_catalog_creates_product_and_variant_when_fresh():
    shop = _make_shop()
    db = _make_db()
    svc = _make_catalog_service()
    cache = {}
    counters = {"products_created": 0, "variants_created": 0}
    row = {
        "Listing ID": "555",
        "Item Name": "Leather Wallet",
        "SKU": "WAL-001",
        "Variations": "Color: Brown",
        "Price": "49.99",
    }

    variant = await _ensure_catalog_row(db, shop, svc, row, cache, counters)

    assert isinstance(variant, ProductVariant)
    assert variant.sku == "WAL-001"
    assert variant.variant_name == "Color: Brown"
    assert variant.price == Decimal("49.99")
    assert variant.weight_g == 0
    assert variant.length_mm == 0
    assert variant.width_mm == 0
    assert variant.height_mm == 0
    assert counters == {"products_created": 1, "variants_created": 1}

    added = [c.args[0] for c in db.add.call_args_list]
    products = [a for a in added if isinstance(a, Product)]
    variants = [a for a in added if isinstance(a, ProductVariant)]
    assert len(products) == 1
    assert products[0].external_ref == "555"
    assert products[0].title == "Leather Wallet"
    assert variants == [variant]


@pytest.mark.asyncio
async def test_ensure_catalog_returns_none_for_blank_listing_id():
    shop = _make_shop()
    db = _make_db()
    svc = _make_catalog_service()
    counters = {"products_created": 0, "variants_created": 0}

    result = await _ensure_catalog_row(
        db, shop, svc, {"Listing ID": "", "SKU": "X"}, {}, counters
    )

    assert result is None
    assert counters == {"products_created": 0, "variants_created": 0}
    db.add.assert_not_called()
    svc.find_product_by_external_ref.assert_not_called()


@pytest.mark.asyncio
async def test_ensure_catalog_skips_variant_when_sku_shop_wide_taken_and_no_product_yet():
    """Q7 lazy insert: SKU is taken under a different existing product → no Product is materialized."""
    shop = _make_shop()
    db = _make_db()
    svc = _make_catalog_service(taken_skus={"DUPE-SKU"})
    counters = {"products_created": 0, "variants_created": 0}
    row = {"Listing ID": "777", "Item Name": "Belt", "SKU": "DUPE-SKU", "Price": "10"}

    result = await _ensure_catalog_row(db, shop, svc, row, {}, counters)

    assert result is None
    assert counters == {"products_created": 0, "variants_created": 0}
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_ensure_catalog_lazy_product_no_orphan_when_all_variants_blocked():
    """Q7: every variant of a fresh listing collides shop-wide → no Product row is left behind."""
    shop = _make_shop()
    db = _make_db()
    svc = _make_catalog_service(taken_skus={"SKU-A", "SKU-B"})
    counters = {"products_created": 0, "variants_created": 0}
    cache = {}
    rows = [
        {"Listing ID": "888", "Item Name": "Hat", "SKU": "SKU-A", "Price": "5"},
        {"Listing ID": "888", "Item Name": "Hat", "SKU": "SKU-B", "Price": "5"},
    ]

    for r in rows:
        assert await _ensure_catalog_row(db, shop, svc, r, cache, counters) is None

    assert counters == {"products_created": 0, "variants_created": 0}
    added_products = [c.args[0] for c in db.add.call_args_list if isinstance(c.args[0], Product)]
    assert added_products == []


@pytest.mark.asyncio
async def test_ensure_catalog_in_import_idempotency_same_listing_repeated():
    """Same Listing ID across N CSV rows → 1 Product, deduplicated variants per effective SKU."""
    shop = _make_shop()
    db = _make_db()
    svc = _make_catalog_service()
    counters = {"products_created": 0, "variants_created": 0}
    cache = {}
    row = {"Listing ID": "999", "Item Name": "Bag", "SKU": "BAG-1", "Price": "20"}

    v1 = await _ensure_catalog_row(db, shop, svc, row, cache, counters)
    v2 = await _ensure_catalog_row(db, shop, svc, row, cache, counters)
    v3 = await _ensure_catalog_row(db, shop, svc, row, cache, counters)

    assert v1 is v2 is v3
    assert counters == {"products_created": 1, "variants_created": 1}
    # find_product_by_external_ref should only fire on first row (cache covers the rest).
    assert svc.find_product_by_external_ref.await_count == 1


@pytest.mark.asyncio
async def test_ensure_catalog_blank_sku_fallback_within_listing():
    shop = _make_shop()
    db = _make_db()
    svc = _make_catalog_service()
    counters = {"products_created": 0, "variants_created": 0}
    cache = {}
    rows = [
        {"Listing ID": "111", "Item Name": "Strap", "SKU": "", "Variations": "Black"},
        {"Listing ID": "111", "Item Name": "Strap", "SKU": "", "Variations": "Tan"},
        {"Listing ID": "111", "Item Name": "Strap", "SKU": "", "Variations": "Cognac"},
    ]

    variants = [await _ensure_catalog_row(db, shop, svc, r, cache, counters) for r in rows]

    skus = [v.sku for v in variants]
    assert all(re.match(r"^etsy-111-[0-9a-f]{8}$", s) for s in skus)
    assert len(set(skus)) == 3
    assert counters == {"products_created": 1, "variants_created": 3}


@pytest.mark.asyncio
async def test_ensure_catalog_dedups_blank_sku_by_variations():
    """BUG-5: 5 rows under one listing with 2 distinct normalized Variations
    groups (whitespace + case mixed across rows) → 1 Product + 2 Variants.
    Calls 2..5 hit the variants_by_sku cache and return the same instances."""
    shop = _make_shop()
    db = _make_db()
    svc = _make_catalog_service()
    counters = {"products_created": 0, "variants_created": 0}
    cache = {}
    rows = [
        # Group A: "color:red,pakning:single bat id" — 3 rows w/ whitespace+case variation
        {"Listing ID": "L", "Item Name": "Holder", "SKU": "",
         "Variations": "Color:Red,Pakning:Single Bat ID"},
        {"Listing ID": "L", "Item Name": "Holder", "SKU": "",
         "Variations": "color:red, pakning:single bat id"},
        {"Listing ID": "L", "Item Name": "Holder", "SKU": "",
         "Variations": "  Color:Red,Pakning:Single Bat ID  "},
        # Group B: "color:red,pakning:bat id with gift box" — 2 rows
        {"Listing ID": "L", "Item Name": "Holder", "SKU": "",
         "Variations": "Color:Red,Pakning:Bat ID with Gift Box"},
        {"Listing ID": "L", "Item Name": "Holder", "SKU": "",
         "Variations": "COLOR:RED,PAKNING:BAT ID WITH GIFT BOX"},
    ]

    variants = [await _ensure_catalog_row(db, shop, svc, r, cache, counters) for r in rows]

    assert counters == {"products_created": 1, "variants_created": 2}
    # First-writer-wins: rows 0 and 3 produce the two ProductVariant instances;
    # rows 1, 2 reuse row 0; row 4 reuses row 3.
    assert variants[0] is variants[1] is variants[2]
    assert variants[3] is variants[4]
    assert variants[0] is not variants[3]
    # Same product_id under one Product.
    assert variants[0].product_id == variants[3].product_id
    # Both SKUs match the hashed pattern; pairwise distinct.
    skus = {variants[0].sku, variants[3].sku}
    assert len(skus) == 2
    assert all(re.match(r"^etsy-L-[0-9a-f]{8}$", s) for s in skus)
    # variant_name preserves the first-writer original Variations text (untouched).
    assert variants[0].variant_name == "Color:Red,Pakning:Single Bat ID"
    assert variants[3].variant_name == "Color:Red,Pakning:Bat ID with Gift Box"


@pytest.mark.asyncio
async def test_ensure_catalog_reuses_existing_product_no_new_product_count():
    """Re-import: existing Product already in DB. New unique variant adds under it; products_created stays 0."""
    shop = _make_shop()
    db = _make_db()

    existing = MagicMock(spec=Product)
    existing.id = uuid4()
    existing.shop_id = shop.id
    existing.external_ref = "222"
    existing.variants = []  # no variants yet

    svc = _make_catalog_service(existing_product=existing)
    counters = {"products_created": 0, "variants_created": 0}
    row = {"Listing ID": "222", "Item Name": "Notebook", "SKU": "NB-1", "Price": "8"}

    variant = await _ensure_catalog_row(db, shop, svc, row, {}, counters)

    assert isinstance(variant, ProductVariant)
    assert variant.product_id == existing.id
    assert counters == {"products_created": 0, "variants_created": 1}
    assert all(not isinstance(c.args[0], Product) for c in db.add.call_args_list)


@pytest.mark.asyncio
async def test_ensure_catalog_skips_existing_variant_under_existing_product():
    """Re-import same CSV: existing Product + existing matching variant → no new rows added."""
    shop = _make_shop()
    db = _make_db()

    existing_variant = MagicMock(spec=ProductVariant)
    existing_variant.id = uuid4()
    existing_variant.sku = "NB-1"

    existing_product = MagicMock(spec=Product)
    existing_product.id = uuid4()
    existing_product.shop_id = shop.id
    existing_product.external_ref = "333"
    existing_product.variants = [existing_variant]

    svc = _make_catalog_service(existing_product=existing_product, taken_skus={"NB-1"})
    counters = {"products_created": 0, "variants_created": 0}
    row = {"Listing ID": "333", "Item Name": "Notebook", "SKU": "NB-1", "Price": "8"}

    variant = await _ensure_catalog_row(db, shop, svc, row, {}, counters)

    assert variant is existing_variant
    assert counters == {"products_created": 0, "variants_created": 0}
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_ensure_catalog_truncates_long_variations_to_255():
    shop = _make_shop()
    db = _make_db()
    svc = _make_catalog_service()
    counters = {"products_created": 0, "variants_created": 0}
    long_text = "x" * 400

    variant = await _ensure_catalog_row(
        db, shop, svc,
        {"Listing ID": "444", "Item Name": "Item", "SKU": "S", "Variations": long_text},
        {}, counters,
    )

    assert variant is not None
    assert variant.variant_name is not None
    assert len(variant.variant_name) == 255


# ---------- parse_etsy_csv (integration-ish) ----------


def _csv_bytes(rows):
    """Build a minimal Etsy-shaped CSV from a list of row dicts."""
    headers = [
        "Sale ID", "Sale Date", "Buyer", "Buyer Email",
        "Item Name", "SKU", "Listing ID", "Variations",
        "Quantity", "Price", "Order Total", "Currency",
        "Ship Country", "Ship Name", "Ship Address1", "Ship City",
    ]
    out = [",".join(headers)]
    for row in rows:
        out.append(",".join(str(row.get(h, "")) for h in headers))
    return ("\n".join(out) + "\n").encode("utf-8")


@pytest.mark.asyncio
async def test_parse_etsy_csv_threads_counters_and_links_order_items():
    shop = _make_shop()
    db = _make_db()
    # No existing order — the duplicate-check query returns None.
    no_existing = MagicMock()
    no_existing.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=no_existing)

    customer = MagicMock()
    customer.id = uuid4()

    csv_bytes = _csv_bytes([
        {
            "Sale ID": "S-1", "Sale Date": "2026-01-15",
            "Buyer": "Alice", "Buyer Email": "a@example.com",
            "Item Name": "Wallet", "SKU": "", "Listing ID": "L-100",
            "Variations": "Color: Brown",
            "Quantity": "1", "Price": "30", "Order Total": "30",
            "Currency": "USD", "Ship Country": "US",
            "Ship Name": "Alice", "Ship Address1": "1 St", "Ship City": "NYC",
        },
        {
            "Sale ID": "S-1", "Sale Date": "2026-01-15",
            "Buyer": "Alice", "Buyer Email": "a@example.com",
            "Item Name": "Wallet", "SKU": "", "Listing ID": "L-100",
            "Variations": "Color: Tan",
            "Quantity": "1", "Price": "30", "Order Total": "30",
            "Currency": "USD", "Ship Country": "US",
            "Ship Name": "Alice", "Ship Address1": "1 St", "Ship City": "NYC",
        },
    ])

    fake_svc = _make_catalog_service()
    with patch("services.etsy_parser.upsert_customer", AsyncMock(return_value=customer)), \
         patch("services.etsy_parser.CatalogService", return_value=fake_svc):
        result = await parse_etsy_csv(db, shop, csv_bytes, user_id=uuid4())

    assert result.imported == 1
    assert result.skipped == 0
    assert result.products_created == 1
    assert result.variants_created == 2  # two distinct Variations groups → two hashed SKUs

    from models.order import OrderItem
    items = [c.args[0] for c in db.add.call_args_list if isinstance(c.args[0], OrderItem)]
    assert len(items) == 2
    assert all(i.product_variant_id is not None for i in items)
    assert all(i.snapshot_weight_g is None for i in items)  # snapshot copy intentionally skipped

    # Each variant SKU must be content-keyed: etsy-L-100-{8 hex chars}, distinct.
    variant_objs = [c.args[0] for c in db.add.call_args_list if isinstance(c.args[0], ProductVariant)]
    skus = [v.sku for v in variant_objs]
    assert len(skus) == 2
    assert all(re.match(r"^etsy-L-100-[0-9a-f]{8}$", s) for s in skus)
    assert len(set(skus)) == 2


@pytest.mark.asyncio
async def test_parse_etsy_csv_blank_listing_id_does_not_abort_import():
    shop = _make_shop()
    db = _make_db()
    no_existing = MagicMock()
    no_existing.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=no_existing)

    customer = MagicMock()
    customer.id = uuid4()

    csv_bytes = _csv_bytes([{
        "Sale ID": "S-2", "Sale Date": "2026-01-16",
        "Buyer": "Bob", "Buyer Email": "b@example.com",
        "Item Name": "Mystery", "SKU": "", "Listing ID": "",  # blank
        "Variations": "",
        "Quantity": "1", "Price": "10", "Order Total": "10",
        "Currency": "USD", "Ship Country": "US",
        "Ship Name": "Bob", "Ship Address1": "1 St", "Ship City": "NYC",
    }])

    fake_svc = _make_catalog_service()
    with patch("services.etsy_parser.upsert_customer", AsyncMock(return_value=customer)), \
         patch("services.etsy_parser.CatalogService", return_value=fake_svc):
        result = await parse_etsy_csv(db, shop, csv_bytes, user_id=uuid4())

    assert result.imported == 1
    assert result.products_created == 0
    assert result.variants_created == 0
    fake_svc.find_product_by_external_ref.assert_not_called()
