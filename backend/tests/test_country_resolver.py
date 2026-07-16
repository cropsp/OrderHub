"""ETSY-COUNTRY-FIX — country name → ISO alpha-2 resolver.

Covers services.country_resolver.resolve_country_code, which replaces the
`Ship Country`[:2] truncation in the Etsy CSV parser.
"""
import pytest

from services.country_resolver import COUNTRY_NAME_ALIASES, resolve_country_code


# ---------- names seen in the real Etsy data ----------


@pytest.mark.parametrize(
    "name, expected",
    [
        ("United States", "US"),
        ("United Kingdom", "GB"),
        ("Germany", "DE"),  # the CTRY-1 symptom: "Ge" used to render as Georgia
        ("Czech Republic", "CZ"),
        ("France", "FR"),
        ("Italy", "IT"),
        ("Canada", "CA"),
        ("Ukraine", "UA"),
    ],
)
def test_resolves_country_names_present_in_data(name, expected):
    assert resolve_country_code(name) == expected


# ---------- names pycountry misses; covered by the alias overlay ----------


@pytest.mark.parametrize(
    "name, expected",
    [
        ("UK", "GB"),
        ("U.K.", "GB"),
        ("Great Britain", "GB"),
        ("England", "GB"),
        ("USA", "US"),
        ("Russia", "RU"),
        ("Turkey", "TR"),
        ("Ivory Coast", "CI"),
        # search_fuzzy resolves this to KP (North Korea) — the alias must win.
        ("Republic of Korea", "KR"),
    ],
)
def test_resolves_aliases(name, expected):
    assert resolve_country_code(name) == expected


def test_south_korea_is_not_north_korea():
    """Regression guard: fuzzy matching mapped Korea variants to KP."""
    assert resolve_country_code("South Korea") == "KR"
    assert resolve_country_code("Republic of Korea") == "KR"
    assert resolve_country_code("North Korea") == "KP"


# ---------- already-valid codes pass through ----------


@pytest.mark.parametrize("code, expected", [("US", "US"), ("us", "US"), ("gb", "GB")])
def test_existing_iso_codes_pass_through(code, expected):
    assert resolve_country_code(code) == expected


def test_real_two_letter_code_is_not_treated_as_a_name():
    """A literal "GE" is Georgia. Only the name "Germany" becomes DE."""
    assert resolve_country_code("GE") == "GE"
    assert resolve_country_code("Germany") == "DE"


# ---------- normalization ----------


@pytest.mark.parametrize("name", ["  France  ", "FRANCE", "france", "France"])
def test_case_and_whitespace_insensitive(name):
    assert resolve_country_code(name) == "FR"


# ---------- unresolvable → None, never a guess ----------


@pytest.mark.parametrize("value", [None, "", "   ", "Elbonia", "Zz", "???"])
def test_unresolvable_returns_none(value):
    assert resolve_country_code(value) is None


def test_alias_values_are_all_valid_iso_codes():
    import pycountry

    for name, code in COUNTRY_NAME_ALIASES.items():
        assert pycountry.countries.get(alpha_2=code) is not None, f"{name} -> {code}"
