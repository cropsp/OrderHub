"""FX-CONVERSION — the direction guard.

NBU publishes UAH per 1 USD. Converting a UAH cost into USD is therefore a
DIVISION. Multiplying instead produces a number that is ~1900x too large but still
looks like money in a P&L, and nothing downstream would catch it: finance sums it,
partner payouts pay against it, and the order snapshot is frozen at ship.

So this file pins the direction with concrete numbers and asserts the multiplied
value is nowhere near the divided one. It is deliberately separate from the other
FX tests: if someone "simplifies" fx_service by normalising to a multiplier, this
is the file that should fail first and unambiguously.
"""
from decimal import Decimal

import pytest

from services.fx_service import FxRates, FxUnsupported


# 190.43 UAH is the real Bat ID Wallet BOM total from docs/warehouse/bom-intake.md.
BASIS_UAH = Decimal("190.43")
RATE = Decimal("41.5")  # UAH per 1 USD
EXPECTED_USD = Decimal("4.59")  # 190.43 / 41.5 = 4.588... -> 4.59 at 2dp


def _rates(rate: Decimal = RATE) -> FxRates:
    return FxRates(uah_per_usd=rate, source="manual")


def test_uah_to_usd_divides_by_the_nbu_rate():
    got = _rates().convert(BASIS_UAH, frm="UAH", to="USD")
    assert got.quantize(Decimal("0.01")) == EXPECTED_USD


def test_uah_to_usd_is_not_multiplication():
    """The inversion bug, stated as an assertion.

    190.43 * 41.5 = 7902.85 — a plausible-looking figure that is 1722x the truth.
    """
    got = _rates().convert(BASIS_UAH, frm="UAH", to="USD")
    multiplied = BASIS_UAH * RATE

    assert got < BASIS_UAH, "UAH->USD must shrink the number; UAH is the weaker unit"
    assert got != multiplied
    # Not merely different — different by three orders of magnitude.
    assert multiplied / got > Decimal("1000")
    assert abs(got - multiplied) > Decimal("7000")


def test_usd_to_uah_multiplies():
    """The inverse direction, so the pair cannot be quietly made symmetric."""
    got = _rates().convert(Decimal("4.588674698795180722891566265"), frm="USD", to="UAH")
    assert got.quantize(Decimal("0.01")) == BASIS_UAH


def test_round_trip_returns_the_original():
    usd = _rates().convert(BASIS_UAH, frm="UAH", to="USD")
    back = _rates().convert(usd, frm="USD", to="UAH")
    assert back.quantize(Decimal("0.01")) == BASIS_UAH


def test_convert_returns_unrounded_value():
    """Callers quantize ONCE at the end of their fold. If convert() rounded here,
    a multi-bucket order would round per bucket and diverge from the preview."""
    got = _rates().convert(BASIS_UAH, frm="UAH", to="USD")
    assert got != got.quantize(Decimal("0.01"))
    assert str(got).startswith("4.588")


def test_same_currency_is_identity_and_needs_no_rate():
    """KoraKlenu: UAH materials in a UAH order. No rate involved at all."""
    none_available = FxRates.unavailable()
    assert none_available.convert(BASIS_UAH, frm="UAH", to="UAH") == BASIS_UAH
    assert none_available.can_convert(frm="UAH", to="UAH") is True
    assert none_available.rate_for(frm="UAH", to="UAH") is None


def test_rate_for_reports_the_stamped_rate():
    assert _rates().rate_for(frm="UAH", to="USD") == RATE
    assert _rates().rate_for(frm="USD", to="UAH") == RATE


def test_currency_codes_are_normalised_before_dispatch():
    """Material.currency is a bare String(3) with no CHECK — ' uah ' must not
    become an unknown pair once currency is a lookup key."""
    got = _rates().convert(BASIS_UAH, frm=" uah ", to="usd")
    assert got.quantize(Decimal("0.01")) == EXPECTED_USD


@pytest.mark.parametrize("frm,to", [("EUR", "USD"), ("UAH", "EUR"), ("GBP", "PLN")])
def test_unknown_pairs_raise_rather_than_guess(frm, to):
    """Task rule 1: any currency other than UAH/USD degrades. It must never be
    converted at the USD rate."""
    assert _rates().can_convert(frm=frm, to=to) is False
    with pytest.raises(FxUnsupported):
        _rates().convert(BASIS_UAH, frm=frm, to=to)


def test_no_rate_means_no_conversion():
    unavailable = FxRates.unavailable()
    assert unavailable.can_convert(frm="UAH", to="USD") is False
    with pytest.raises(FxUnsupported):
        unavailable.convert(BASIS_UAH, frm="UAH", to="USD")
