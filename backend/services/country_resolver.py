"""
OrderHub CRM — Country name → ISO 3166-1 alpha-2 resolver (ETSY-COUNTRY-FIX)

The Etsy CSV "Ship Country" column holds a full country *name*. Callers need an
ISO alpha-2 code for `Order.shipping_country` / `Customer.country`, both of which
are VARCHAR(2).

Deliberately conservative: an input that cannot be resolved with confidence
returns None rather than a guess. `pycountry.countries.search_fuzzy` is NOT used
here — it resolves "Republic of Korea" to KP (North Korea) and ranks Uganda first
for "UK", i.e. it produces confidently-wrong codes. A None (caller logs a warning
and stores NULL) is recoverable; a wrong country silently shipped is not.
"""

import re
from typing import Optional

import pycountry

# Names pycountry's name / official_name / common_name lookups do NOT resolve.
# Keys are normalized (see _normalize): casefolded, punctuation-free, single-spaced.
# Extend this map when an import logs an "unresolvable Ship Country" warning.
COUNTRY_NAME_ALIASES: dict[str, str] = {
    # United Kingdom + constituent countries
    "uk": "GB",
    "usa": "US",
    "great britain": "GB",
    "england": "GB",
    "scotland": "GB",
    "wales": "GB",
    "northern ireland": "GB",
    # ISO short names that differ from common usage
    "russia": "RU",
    "turkey": "TR",
    "turkiye": "TR",
    "republic of korea": "KR",
    "ivory coast": "CI",
    "cape verde": "CV",
    "swaziland": "SZ",
    "burma": "MM",
    "macau": "MO",
    "macedonia": "MK",
    "brunei": "BN",
    "palestine": "PS",
    "vatican city": "VA",
    "democratic republic of the congo": "CD",
    "republic of the congo": "CG",
}

_ALPHA2_RE = re.compile(r"^[A-Za-z]{2}$")


def _normalize(value: str) -> str:
    """Casefold, drop punctuation, collapse whitespace — for alias matching."""
    cleaned = re.sub(r"[.,]", "", value)
    return re.sub(r"\s+", " ", cleaned).strip().casefold()


def resolve_country_code(value: Optional[str]) -> Optional[str]:
    """Resolve a country name (or code) to an ISO 3166-1 alpha-2 code.

    Returns None when the value is blank or cannot be resolved confidently;
    callers are expected to log the raw value and store NULL.
    """
    if not value or not value.strip():
        return None

    raw = value.strip()

    # An input that is already a real ISO alpha-2 code passes through. Note this
    # means a literal "GE" stays Georgia — only the *name* "Germany" becomes DE.
    if _ALPHA2_RE.match(raw) and pycountry.countries.get(alpha_2=raw.upper()):
        return raw.upper()

    normalized = _normalize(raw)

    alias = COUNTRY_NAME_ALIASES.get(normalized)
    if alias:
        return alias

    for field in ("name", "official_name", "common_name"):
        # pycountry's lookups are case-sensitive; try the raw form and a
        # title-cased form so "GERMANY" / "germany" both resolve.
        for candidate in (raw, raw.title()):
            match = pycountry.countries.get(**{field: candidate})
            if match:
                return match.alpha_2

    return None
