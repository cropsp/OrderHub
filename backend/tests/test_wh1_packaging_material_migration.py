"""WH-1 migration — the parts that are checkable without a database.

The SQL itself is verified by the round trip
`alembic upgrade head && alembic downgrade -1 && alembic upgrade head`, which is
the only thing that can prove the carrier table really makes a re-upgrade
idempotent. What IS worth freezing here is everything a later edit could quietly
get wrong: the revision it hangs off, the backfill values (rule 4 of the sprint
spec), and the fact that upgrade and downgrade name the SAME carrier table — if
they ever drift apart, a downgrade parks its rows where the next upgrade will
never look and every box silently gains a second material.

Loaded by file path: alembic/versions is not an importable package. Same pattern
as tests/test_etsy_country_backfill.py.
"""

import importlib.util
from pathlib import Path

import pytest

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "e9b2f4c7a318_wh1_packaging_material.py"
)


@pytest.fixture(scope="module")
def module():
    spec = importlib.util.spec_from_file_location("wh1_migration", MIGRATION)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_hangs_off_partner_config_1(module):
    assert module.revision == "e9b2f4c7a318"
    assert module.down_revision == "d7f3a1c85e92"


def test_backfill_values_match_the_spec(module):
    """Frozen in the migration rather than imported from catalog_service, so a
    later change to the app's defaults cannot rewrite history."""
    assert module._MATERIAL_DEFAULTS == {
        "unit": "шт",
        "currency": "UAH",
        "current_unit_cost": 0,
        "stock_quantity": 0,
        "low_stock_threshold": 0,
        "waste_percent": 0,
        "category": "PACKAGING",
        "is_stock_tracked": True,
        "is_active": True,
    }


def test_backfilled_stock_starts_at_zero(module):
    """Deliberately stale: packaging_boxes keeps its counter in WH-1 and WH-2
    copies it over when the consumption trigger moves. Restating it as its own
    assertion so 'fixing' it here reads as the WH-2 decision it actually is."""
    assert module._MATERIAL_DEFAULTS["stock_quantity"] == 0


def test_upgrade_and_downgrade_share_one_carrier_table(module):
    """The carrier is the only thing that survives a downgrade to re-identify a
    backfilled material — `packaging_boxes.material_id` and `materials.category`
    are both dropped, and material names are not unique."""
    assert module.LINK_TABLE == "wh1_packaging_material_link"
    assert module.LINK_TABLE in module.LINK_TABLE_DDL
    assert "CREATE TABLE IF NOT EXISTS" in module.LINK_TABLE_DDL

    source = MIGRATION.read_text(encoding="utf-8")
    upgrade_src = source.split("def upgrade()")[1].split("def downgrade()")[0]
    downgrade_src = source.split("def downgrade()")[1]

    # Both halves must reach the carrier through the constant, never a literal.
    assert "LINK_TABLE_DDL" in upgrade_src and "LINK_TABLE_DDL" in downgrade_src
    assert '"wh1_packaging_material_link"' not in upgrade_src
    assert '"wh1_packaging_material_link"' not in downgrade_src


def test_downgrade_deletes_no_materials(module):
    """A backfilled material may carry receipts and movements by downgrade time,
    and both cascade on delete. The downgrade drops columns only."""
    downgrade_src = MIGRATION.read_text(encoding="utf-8").split("def downgrade()")[1]
    assert "DELETE FROM MATERIALS" not in downgrade_src.upper()
    assert "drop_column" in downgrade_src
