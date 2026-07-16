"""COUNTRY-CLEANUP — residual country-code cleanup disambiguation rules.

The migration (alembic/versions/f2a9c4d7e1b8_cleanup_residual_country_codes.py) is
deliberately self-contained, so its pure `_resolve_row` helper is loaded here by
path — alembic/versions is not an importable package.

The SQL side (ETSY-only scope guard, УК→UA customer fix, backup tables, downgrade)
is verified by the migration round-trip + SQL checks documented in the sprint, not
here: the test suite is mock-based and has no database.
"""
import importlib.util
from pathlib import Path

import pytest

_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "f2a9c4d7e1b8_cleanup_residual_country_codes.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("country_cleanup", _MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


migration = _load_migration()
_resolve_row = migration._resolve_row


# ---------- unambiguous name-prefix truncations ----------


@pytest.mark.parametrize(
    "code, expected",
    [("Be", "BE"), ("Is", "IL"), ("Ja", "JP"), ("Ma", "MY"), ("Sp", "ES"), ("Tü", "TR")],
)
def test_unambiguous_truncations(code, expected):
    assert _resolve_row(code, None, None) == expected


def test_truncations_ignore_address_shape():
    """The unambiguous map is keyed on the code alone; address fields are irrelevant."""
    assert _resolve_row("Ja", "神奈川県", "2520233") == "JP"
    assert _resolve_row("Ma", "Selangor", "47630") == "MY"
    assert _resolve_row("Tü", "Istanbul", "34740") == "TR"


# ---------- "Sw" → CH vs SE, by postal-code length ----------


@pytest.mark.parametrize("zip_", ["1284", "6616", "8118", "1000", "9999"])
def test_sw_with_4_digit_zip_resolves_ch(zip_):
    # Switzerland uses 4-digit postal codes (Chancy 1284, Losone 6616, Pfaffhausen 8118).
    assert _resolve_row("Sw", None, zip_) == "CH"
    assert _resolve_row("Sw", "GE", "1284") == "CH"  # canton code present, still CH


@pytest.mark.parametrize("zip_", ["75659", "11122", "10000"])
def test_sw_with_5_digit_zip_resolves_se(zip_):
    # Sweden uses 5-digit postal codes (Uppsala 75659).
    assert _resolve_row("Sw", "Uppsala", zip_) == "SE"


def test_sw_without_usable_zip_is_unresolvable():
    assert _resolve_row("Sw", None, None) is None
    assert _resolve_row("Sw", "", "") is None
    assert _resolve_row("Sw", None, "ABC") is None  # non-numeric
    assert _resolve_row("Sw", None, "123") is None  # 3-digit — neither shape
    assert _resolve_row("Sw", None, "123456") is None  # 6-digit — neither shape


# ---------- never guess ----------


@pytest.mark.parametrize("code", ["Zz", "Xx", "US", "DE", "Ge", "Un", ""])
def test_unknown_codes_are_left_untouched(code):
    """Anything outside the enumerated residual set resolves to None (skip + report).

    Note "Ge"/"Un" were handled by the earlier ETSY-COUNTRY-FIX backfill and are not
    this migration's concern — it must not re-touch them.
    """
    assert _resolve_row(code, "CA", "90210") is None
