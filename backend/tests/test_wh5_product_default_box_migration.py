"""WH-5 migration — the parts that are checkable without a database.

The DDL itself is proven by the round trip `alembic upgrade head && alembic
downgrade -1 && alembic upgrade head`. What is worth freezing here is what a later
edit could quietly get wrong:

  - the revision it hangs off (a wrong parent puts the column before the WH-2
    counters move, and the model would disagree with the schema);
  - that the column is NULLABLE with no default and no backfill — there is no
    honest box to guess, and a wrong one would be consumed at SHIPPED and priced
    into COGS;
  - that the FK is named, and named the SAME in upgrade and downgrade — an
    unnamed constraint gets a server-generated name that a later autogenerate
    keeps wanting to "fix", and a downgrade that names it differently cannot drop
    it at all;
  - ondelete=SET NULL, matching the two existing FKs from orders to the same
    table.

Loaded by file path: alembic/versions is not an importable package. Same pattern
as tests/test_wh1_packaging_material_migration.py and its WH-2 sibling.
"""

import importlib.util
import inspect
from pathlib import Path

import pytest

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "a3c5e7b91d40_wh5_product_default_packaging_box.py"
)


@pytest.fixture(scope="module")
def module():
    spec = importlib.util.spec_from_file_location("wh5_migration", MIGRATION)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_hangs_off_the_wh2_counter_migration(module):
    assert module.revision == "a3c5e7b91d40"
    assert module.down_revision == "f2a7c1d84b63"


def test_column_is_nullable_with_no_default_and_no_backfill(module):
    source = inspect.getsource(module.upgrade)

    assert "nullable=True" in source
    assert "server_default" not in source
    # A data backfill here would have to invent which box each product ships in.
    # Runbook Phase 3 populates it by hand, per product.
    assert "UPDATE" not in source.upper()


def test_the_foreign_key_is_named_and_set_null(module):
    up = inspect.getsource(module.upgrade)
    down = inspect.getsource(module.downgrade)

    assert module.FK_NAME == "fk_products_default_packaging_box_id"
    assert 'ondelete="SET NULL"' in up
    # Both sides must name the same constraint or the downgrade cannot drop it.
    assert "FK_NAME" in up and "FK_NAME" in down


def test_downgrade_drops_the_constraint_before_the_column(module):
    source = inspect.getsource(module.downgrade)

    assert source.index("drop_constraint") < source.index("drop_column")


def test_the_model_matches_the_migration():
    """A column added to one and not the other is the classic drift."""
    from models.product import Product

    column = Product.__table__.c.default_packaging_box_id
    assert column.nullable is True
    assert column.server_default is None

    fk = next(iter(column.foreign_keys))
    assert fk.column.table.name == "packaging_boxes"
    assert fk.ondelete == "SET NULL"
    assert fk.constraint.name == "fk_products_default_packaging_box_id"
