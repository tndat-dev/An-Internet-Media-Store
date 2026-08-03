import pytest

from apps.carts.services import validate_cart_item_quantity


@pytest.mark.parametrize(
    "requested_quantity,stock_quantity,expected",
    [
        (
            1,
            10,
            {"valid": True, "reason": None, "missing_quantity": 0},
        ),
        (
            10,
            10,
            {"valid": True, "reason": None, "missing_quantity": 0},
        ),
        (
            11,
            10,
            {
                "valid": False,
                "reason": "INSUFFICIENT_STOCK",
                "missing_quantity": 1,
            },
        ),
        (
            0,
            10,
            {"valid": False, "reason": "INVALID_QUANTITY", "missing_quantity": 0},
        ),
        (
            -1,
            10,
            {"valid": False, "reason": "INVALID_QUANTITY", "missing_quantity": 0},
        ),
        (
            5,
            0,
            {
                "valid": False,
                "reason": "INSUFFICIENT_STOCK",
                "missing_quantity": 5,
            },
        ),
        (
            5,
            -1,
            {"valid": False, "reason": "INVALID_STOCK", "missing_quantity": 0},
        ),
    ],
)
def test_validate_cart_item_quantity(
    requested_quantity,
    stock_quantity,
    expected,
):
    assert validate_cart_item_quantity(requested_quantity, stock_quantity) == expected
