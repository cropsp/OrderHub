"""MAT-6 — receipts-by-invoice read.

Same compile-SQL pattern as test_materials_router.py: a mocked AsyncSession
captures the statements and the compiled SQL is asserted on.

The behaviour worth pinning is that this read spans **both** ledgers. Two of the
eight invoices in the first real load (1996637412, 1996638845) carry an overhead
line — a cutting service, a finishing compound — alongside their leather, so a
direct-only view would silently return an invoice that cannot tie to its paper
total.
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from models.material import MaterialReceipt, OverheadMaterialReceipt
from routers.receipts import list_receipts_by_invoice


def _make_db(material_rows=(), overhead_rows=()):
    """AsyncSession mock returning the two row sets in call order."""
    captured: list = []
    batches = [list(material_rows), list(overhead_rows)]

    async def fake_execute(stmt):
        captured.append(stmt)
        r = MagicMock()
        r.all.return_value = batches[len(captured) - 1] if len(captured) <= 2 else []
        return r

    db = MagicMock()
    db.execute = AsyncMock(side_effect=fake_execute)
    return db, captured


def _compiled(stmt) -> str:
    return str(
        stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    ).lower()


def _material_receipt(**over):
    base = dict(
        id=uuid.uuid4(),
        material_id=uuid.uuid4(),
        qty=Decimal("100.00"),
        unit_cost=Decimal("12.7539"),
        currency="UAH",
        shipping_cost=None,
        is_initial=False,
        supplier="ФОП Додон Максим Анатолійович",
        invoice_no="1996637412",
        received_at=datetime(2026, 3, 11, tzinfo=timezone.utc),
        notes=None,
        user_id=uuid.uuid4(),
        created_at=datetime(2026, 8, 2, tzinfo=timezone.utc),
    )
    base.update(over)
    return MaterialReceipt(**base)


def _overhead_receipt(**over):
    base = dict(
        id=uuid.uuid4(),
        overhead_material_id=uuid.uuid4(),
        shop_id=None,
        qty=Decimal("1.00"),
        total_cost=Decimal("80.00"),
        currency="UAH",
        supplier="ФОП Додон Максим Анатолійович",
        invoice_no="1996637412",
        received_at=datetime(2026, 3, 11, tzinfo=timezone.utc),
        notes="Позиція 4, артикул 012056. Послуга порізки шкіри 15%.",
        user_id=uuid.uuid4(),
        created_at=datetime(2026, 8, 2, tzinfo=timezone.utc),
    )
    base.update(over)
    return OverheadMaterialReceipt(**base)


@pytest.mark.asyncio
async def test_both_ledgers_are_filtered_on_the_exact_invoice_no():
    db, stmts = _make_db()

    await list_receipts_by_invoice(
        invoice_no="1996637412", db=db, user=MagicMock()
    )

    assert len(stmts) == 2, f"expected one query per ledger, got {len(stmts)}"
    material_sql, overhead_sql = (_compiled(s) for s in stmts)

    assert "material_receipts.invoice_no = '1996637412'" in material_sql, material_sql
    assert (
        "overhead_material_receipts.invoice_no = '1996637412'" in overhead_sql
    ), overhead_sql
    # Exact match, never a prefix/substring — '199663741' must not pull in
    # '1996637412'.
    assert "ilike" not in material_sql and "like" not in material_sql, material_sql
    assert "ilike" not in overhead_sql and "like" not in overhead_sql, overhead_sql


@pytest.mark.asyncio
async def test_queries_join_their_catalog_table_for_the_display_name():
    """Without the joined name the agent gets bare UUIDs and has to look each one
    up — which is the per-material round-tripping this endpoint replaces."""
    db, stmts = _make_db()

    await list_receipts_by_invoice(invoice_no="X", db=db, user=MagicMock())
    material_sql, overhead_sql = (_compiled(s) for s in stmts)

    assert "join materials" in material_sql, material_sql
    assert "materials.name" in material_sql, material_sql
    assert "join overhead_materials" in overhead_sql, overhead_sql
    assert "overhead_materials.name" in overhead_sql, overhead_sql


@pytest.mark.asyncio
async def test_lines_are_ordered_oldest_first():
    """Invoice reading order — the inverse of the per-material listings, which
    are newest-purchase-first."""
    db, stmts = _make_db()

    await list_receipts_by_invoice(invoice_no="X", db=db, user=MagicMock())
    material_sql, overhead_sql = (_compiled(s) for s in stmts)

    assert "order by material_receipts.received_at" in material_sql, material_sql
    assert "desc" not in material_sql, material_sql
    assert (
        "order by overhead_material_receipts.received_at" in overhead_sql
    ), overhead_sql
    assert "desc" not in overhead_sql, overhead_sql


@pytest.mark.asyncio
async def test_mixed_invoice_returns_both_blocks_with_joined_names():
    """The 1996637412 shape: 3 leather lines + one 80,00 UAH cutting service."""
    db, _stmts = _make_db(
        material_rows=[
            (_material_receipt(), "Шкіра Крейзі Хорс AN 1,4-1,6мм чорна"),
            (_material_receipt(), "Шкіра Крейзі Хорс AN 1,4-1,6мм коньяк"),
            (_material_receipt(), "Шкіра Краст DR 1,2-1,4мм коньяк"),
        ],
        overhead_rows=[(_overhead_receipt(), "Послуга порізки шкіри")],
    )

    result = await list_receipts_by_invoice(
        invoice_no="1996637412", db=db, user=MagicMock()
    )

    assert result.invoice_no == "1996637412"
    assert len(result.material_receipts) == 3
    assert len(result.overhead_receipts) == 1
    assert result.material_receipts[0].material_name == (
        "Шкіра Крейзі Хорс AN 1,4-1,6мм чорна"
    )
    assert result.overhead_receipts[0].overhead_material_name == "Послуга порізки шкіри"
    assert result.overhead_receipts[0].total_cost == Decimal("80.00")
    # Inherited computation still applies to the subclassed line.
    assert result.material_receipts[0].effective_unit_cost == Decimal("12.7539")


@pytest.mark.asyncio
async def test_unknown_invoice_is_200_with_empty_blocks_not_404():
    """An invoice is not an entity here — only a string stamped on receipt rows.
    A 404 would read to the agent as a broken endpoint rather than "no lines"."""
    db, _stmts = _make_db()

    result = await list_receipts_by_invoice(
        invoice_no="NOPE-404", db=db, user=MagicMock()
    )

    assert result.invoice_no == "NOPE-404"
    assert result.material_receipts == []
    assert result.overhead_receipts == []


@pytest.mark.asyncio
async def test_no_server_side_totals_are_exposed():
    """Summing is the reader's job: lines may span currencies, and a total here
    would be a new money field for no gain (MCP passthrough invariant)."""
    from schemas.material import InvoiceReceiptsRead

    assert set(InvoiceReceiptsRead.model_fields) == {
        "invoice_no",
        "material_receipts",
        "overhead_receipts",
    }
