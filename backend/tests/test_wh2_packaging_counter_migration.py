"""WH-2 counter migration — the parts that are checkable without a database.

The SQL is proven by the round trip `alembic upgrade head && alembic downgrade -1
&& alembic upgrade head`; only a real database can show that the carrier really
makes a re-upgrade idempotent. What is worth freezing here is everything a later
edit could quietly get wrong:

  - the revision it hangs off (a wrong parent silently reorders the counter copy
    against WH-1's backfill);
  - the restored server defaults, which are what make a downgraded schema
    identical to the pre-WH-2 head rather than merely similar;
  - that upgrade and downgrade name the SAME carrier table — if they drift, a
    downgrade parks its rows where the next upgrade never looks and every box's
    stock is counted twice;
  - that the copy ADDS stock and only conditionally overwrites the threshold,
    which is the difference between merging an operator's receipts and deleting
    them;
  - that packaging_stock_movements is never touched.

Loaded by file path: alembic/versions is not an importable package. Same pattern
as tests/test_wh1_packaging_material_migration.py.
"""

import importlib.util
import re
from pathlib import Path

import pytest

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "f2a7c1d84b63_wh2_packaging_counters.py"
)


@pytest.fixture(scope="module")
def module():
    spec = importlib.util.spec_from_file_location("wh2_migration", MIGRATION)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def source() -> str:
    return MIGRATION.read_text(encoding="utf-8")


def test_hangs_off_wh1(module):
    assert module.revision == "f2a7c1d84b63"
    assert module.down_revision == "e9b2f4c7a318"


def test_restored_server_defaults_match_the_original_ledger_migration(module):
    """From d8a3f1c4e2b9_add_packaging_stock_ledger.py. Getting these wrong leaves
    a downgraded database that looks right and defaults differently."""
    assert module.BOX_STOCK_SERVER_DEFAULT == "0"
    assert module.BOX_THRESHOLD_SERVER_DEFAULT == "5"


def test_threshold_guard_uses_the_wh1_backfill_value(module):
    """WH-1 backfilled every packaging material's threshold to 0. Only a threshold
    still sitting at that value may be overwritten by the box's — anything else is
    something an operator set through PATCH /api/materials, which does not refuse
    this field."""
    assert module.WH1_BACKFILLED_THRESHOLD == 0


def test_upgrade_and_downgrade_agree_on_the_carrier_table(module, source):
    """The WH-1 lesson, restated: two names here means a silent double-count."""
    assert module.CARRIER_TABLE == "wh2_packaging_counter_carrier"
    assert module.CARRIER_TABLE in module.CARRIER_TABLE_DDL
    # Neither half may hard-code the name past the constant.
    assert '"wh2_packaging_counter_carrier"' not in source.replace(
        f'CARRIER_TABLE = "{module.CARRIER_TABLE}"', ""
    )


def test_stock_is_added_not_assigned(source):
    """A straight assignment would delete any receipt recorded against a packaging
    material since WH-1 — they have been visible in the materials UI the whole
    time. Adding is correct when the material is at WH-1's 0 and non-destructive
    when it is not."""
    upgrade_src = source.split("def upgrade()")[1].split("def downgrade()")[0]
    assert "m.stock_quantity + b.stock_quantity" in upgrade_src
    assert re.search(
        r"SET stock_quantity\s*=\s*b\.stock_quantity", upgrade_src
    ) is None, "the box counter must never simply replace the material's"


def test_reupgrade_subtracts_what_a_downgrade_handed_back(source):
    upgrade_src = source.split("def upgrade()")[1].split("def downgrade()")[0]
    assert "COALESCE(k.restored_qty, 0)" in upgrade_src


def test_threshold_copy_is_guarded(source):
    """Through the constant, not a bare 0 — same rule WH-1's carrier test pins, so
    the guard and the value it guards against can never drift apart."""
    upgrade_src = source.split("def upgrade()")[1].split("def downgrade()")[0]
    assert "AND m.low_stock_threshold = {WH1_BACKFILLED_THRESHOLD}" in upgrade_src


def test_both_columns_are_dropped(source):
    upgrade_src = source.split("def upgrade()")[1].split("def downgrade()")[0]
    assert 'op.drop_column("packaging_boxes", "stock_quantity")' in upgrade_src
    assert 'op.drop_column("packaging_boxes", "low_stock_threshold")' in upgrade_src


def test_downgrade_restores_both_columns(source):
    downgrade_src = source.split("def downgrade()")[1]
    assert downgrade_src.count("op.add_column(") == 2
    assert "ROUND(m.stock_quantity)::int" in downgrade_src


def test_downgrade_does_not_zero_the_materials(source):
    """Zeroing on the way down would leave materials.stock_quantity permanently
    contradicting material_movements for anyone who stayed on the downgraded
    revision. The carrier exists so the round trip can be exact without that."""
    downgrade_src = source.split("def downgrade()")[1]
    assert "SET stock_quantity = 0" not in downgrade_src
    assert "UPDATE materials" not in downgrade_src


def test_the_frozen_packaging_ledger_is_never_touched(source):
    """packaging_stock_movements rows are quantity-only and carry no cost; the
    counters they sum to are exactly what is being copied. Replaying them into
    material_movements would invent a cost history that never existed."""
    body = source.split('"""', 2)[2]  # skip the module docstring
    assert "packaging_stock_movements" not in body
