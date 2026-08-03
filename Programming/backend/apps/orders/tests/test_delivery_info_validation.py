import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[3]

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from apps.orders.validators import (
    validate_customer_name,
    validate_phone_number,
    validate_address,
    validate_delivery_info,
)

# Customer name validation

@pytest.mark.parametrize(
    "name, expected",
    [
        pytest.param("Nguyen Van A", True, id="valid-normal-name"),
        pytest.param(" Tran Thi B ", True, id="valid-trims-outer-spaces"),
        pytest.param("A" * 30, True, id="valid-max-length-30"),
        pytest.param(None, False, id="invalid-name-is-required"),
        pytest.param("", False, id="invalid-empty-name"),
        pytest.param("   ", False, id="invalid-blank-name"),
        pytest.param("A" * 31, False, id="invalid-over-max-length-31"),
        pytest.param("Nguyen123", False, id="invalid-name-with-number"),
        pytest.param("Nguyen@Van", False, id="invalid-name-with-special-char"),
    ],
)
def test_validate_customer_name(name, expected):
    assert validate_customer_name(name) is expected


# Phone number validation
@pytest.mark.parametrize(
    "phone, expected",
    [
        pytest.param("0123456789", True, id="valid-10-digits-starts-with-0"),
        pytest.param("0123-456-789", True, id="valid-dash-separator"),
        pytest.param("0123.456.789", True, id="valid-dot-separator"),
        pytest.param("0123/456/789", True, id="valid-slash-separator"),
        pytest.param(" 0123456789 ", True, id="valid-trims-outer-spaces"),
        pytest.param(None, False, id="invalid-phone-is-required"),
        pytest.param("", False, id="invalid-empty-phone"),
        pytest.param("1234567890", False, id="invalid-does-not-start-with-0"),
        pytest.param("012345678", False, id="invalid-only-9-digits"),
        pytest.param("01234567890", False, id="invalid-11-digits"),
        pytest.param("0123-456/789", False, id="invalid-mixed-separators"),
        pytest.param("0123--456789", False, id="invalid-repeated-separator"),
        pytest.param("0123 456 789", False, id="invalid-spaces-inside"),
        pytest.param("01234abc89", False, id="invalid-contains-letters"),
    ],
)
def test_validate_phone_number(phone, expected):
    assert validate_phone_number(phone) is expected


# Address validation
@pytest.mark.parametrize(
    "address, expected",
    [
        pytest.param("12/5 ABC Street", True, id="valid-normal-address"),
        pytest.param("No 10 Nguyen Trai", True, id="valid-letters-and-numbers"),
        pytest.param("A" * 100, True, id="valid-max-length-100"),
        pytest.param(None, False, id="invalid-address-is-required"),
        pytest.param("", False, id="invalid-empty-address"),
        pytest.param("   ", False, id="invalid-blank-address"),
        pytest.param("A" * 101, False, id="invalid-over-max-length-101"),
        pytest.param("12@ABC", False, id="invalid-unsupported-special-char"),
    ],
)
def test_validate_address(address, expected):
    assert validate_address(address) is expected



# Full delivery info validation
def test_validate_delivery_info_with_all_valid_fields():
    delivery_info = {
        "name": "Nguyen Van A",
        "phone": "0123-456-789",
        "address": "12/5 ABC Street",
    }

    result = validate_delivery_info(delivery_info)

    assert result["valid"] is True
    assert result["errors"] == {}


def test_validate_delivery_info_returns_errors_for_invalid_fields():
    delivery_info = {
        "name": "Nguyen123",
        "phone": "1234567890",
        "address": "12@ABC",
    }

    result = validate_delivery_info(delivery_info)

    assert result["valid"] is False
    assert result["errors"] == {
        "name": "INVALID_CUSTOMER_NAME",
        "phone": "INVALID_PHONE_NUMBER",
        "address": "INVALID_ADDRESS",
    }


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))


def test_validate_delivery_info_handles_missing_fields():
    delivery_info = {}

    result = validate_delivery_info(delivery_info)

    assert result["valid"] is False
    assert result["errors"] == {
        "name": "INVALID_CUSTOMER_NAME",
        "phone": "INVALID_PHONE_NUMBER",
        "address": "INVALID_ADDRESS",
    }
