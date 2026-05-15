"""NP-FIX-3b — Unit tests for normalize_ua_sender_phone helper."""
import pytest
from fastapi import HTTPException

from services.phone_normalization import normalize_ua_sender_phone


def test_normalize_accepts_canonical_380_form():
    assert normalize_ua_sender_phone("380991234567") == "380991234567"


def test_normalize_converts_leading_zero_to_380():
    assert normalize_ua_sender_phone("0991234567") == "380991234567"


def test_normalize_prepends_380_when_country_code_missing():
    assert normalize_ua_sender_phone("991234567") == "380991234567"


def test_normalize_strips_separators_and_plus():
    assert normalize_ua_sender_phone("+380 99 123-45-67") == "380991234567"


def test_normalize_returns_none_for_empty_input():
    assert normalize_ua_sender_phone(None) is None
    assert normalize_ua_sender_phone("") is None
    assert normalize_ua_sender_phone("   ") is None


def test_normalize_rejects_non_numeric_text():
    with pytest.raises(HTTPException) as exc:
        normalize_ua_sender_phone("Іван Петренко")
    assert exc.value.status_code == 422
    assert "Ukrainian mobile" in exc.value.detail


def test_normalize_rejects_wrong_length():
    with pytest.raises(HTTPException) as exc:
        normalize_ua_sender_phone("12345")
    assert exc.value.status_code == 422
