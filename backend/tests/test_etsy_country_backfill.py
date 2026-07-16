"""ETSY-COUNTRY-FIX — backfill migration disambiguation rules.

The migration (alembic/versions/c7d1e93b40af_backfill_etsy_country_codes.py) is
deliberately self-contained, so its pure `_resolve_row` helper is loaded here by
path — alembic/versions is not an importable package.

The SQL side (ETSY-only scope guard, backup table, downgrade) is verified by the
migration round-trip + SQL checks documented in the sprint, not here: the test
suite is mock-based and has no database.
"""
import importlib.util
from pathlib import Path

import pytest

_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "c7d1e93b40af_backfill_etsy_country_codes.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("etsy_country_backfill", _MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


migration = _load_migration()
_resolve_row = migration._resolve_row


# ---------- unambiguous truncations ----------


@pytest.mark.parametrize(
    "code, expected",
    [("Ge", "DE"), ("Cz", "CZ"), ("Fr", "FR"), ("It", "IT"), ("Ca", "CA")],
)
def test_unambiguous_truncations(code, expected):
    assert _resolve_row(code, None, None) == expected


def test_germany_maps_to_de_not_ge():
    """The headline bug: "Ge" rendered as Georgia via Intl.DisplayNames."""
    assert _resolve_row("Ge", None, "63477") == "DE"


# ---------- "Un" → US vs GB, by address shape ----------


@pytest.mark.parametrize(
    "state, zip_",
    [
        ("MD", "20878"),  # the Laureen OBrien smoke case
        ("MA", "02492"),
        ("NY", "10701"),
        ("LA", "70043-5142"),  # ZIP+4
        ("AR", "72761"),
    ],
)
def test_un_with_us_address_shape_resolves_us(state, zip_):
    assert _resolve_row("Un", state, zip_) == "US"


def test_un_with_uk_postcode_resolves_gb():
    # The one real GB row: Selby, North Yorkshire, YO88SZ
    assert _resolve_row("Un", "North Yorkshire", "YO88SZ") == "GB"
    assert _resolve_row("Un", None, "RM6 4TJ") == "GB"


def test_un_without_usable_address_is_unresolvable():
    assert _resolve_row("Un", None, None) is None
    assert _resolve_row("Un", "", "") is None


# ---------- ambiguous codes not present in current data ----------


def test_au_disambiguation():
    assert _resolve_row("Au", "NSW", "2000") == "AU"  # Australia — has a state code
    assert _resolve_row("Au", None, "1010") == "AT"  # Austria — no state code
    assert _resolve_row("Au", None, None) is None


def test_po_disambiguation():
    assert _resolve_row("Po", None, "00-001") == "PL"  # Poland: NN-NNN
    assert _resolve_row("Po", None, "1000-001") == "PT"  # Portugal: NNNN-NNN
    assert _resolve_row("Po", None, "12345") is None


# ---------- never guess ----------


@pytest.mark.parametrize("code", ["Zz", "Xx", "US", "DE", ""])
def test_unknown_codes_are_left_untouched(code):
    """Anything outside the enumerated broken set resolves to None (skip + report)."""
    assert _resolve_row(code, "CA", "90210") is None
