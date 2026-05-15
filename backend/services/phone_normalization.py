"""UA mobile phone normalization for shop NP sender phone (NP-FIX-3b).

Strict variant: raises HTTPException(422) on unparseable input. Distinct
from the lenient inline normalization for recipient phones at
routers/shipping.py:177-183 (which passes unknown shapes through to NP).
Per NP-ROBUSTNESS-1 OQ2 decision, the two are intentionally not unified —
different contracts.
"""

from fastapi import HTTPException


def normalize_ua_sender_phone(raw: str | None) -> str | None:
    """Normalize a UA mobile number to canonical `380XXXXXXXXX` form.

    Accepts: `380XXXXXXXXX`, `0XXXXXXXXX`, `XXXXXXXXX` with arbitrary
    separators / leading `+`. Empty/None → None (sender phone is optional
    per schemas/shop.py).
    """
    if raw is None or raw.strip() == "":
        return None

    digits = "".join(c for c in raw if c.isdigit())

    if len(digits) == 12 and digits.startswith("380"):
        return digits
    if len(digits) == 10 and digits.startswith("0"):
        return "380" + digits[1:]
    if len(digits) == 9:
        return "380" + digits

    raise HTTPException(
        status_code=422,
        detail=(
            "Sender phone must be a Ukrainian mobile number "
            "(e.g. 380XXXXXXXXX or 0XXXXXXXXX)."
        ),
    )
