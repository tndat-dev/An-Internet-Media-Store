from decimal import Decimal

import pytest

from apps.orders.services import calculate_delivery_fee


@pytest.mark.parametrize(
    ("province", "weight_kg", "order_value", "expected_fee"),
    [
        ("Ha Noi", Decimal("3.0"), Decimal("90000"), 22000),
        ("Ha Noi", Decimal("3.5"), Decimal("90000"), 24500),
        ("Ho Chi Minh City", Decimal("3.0"), Decimal("90000"), 22000),
        ("Da Nang", Decimal("0.5"), Decimal("90000"), 30000),
        ("Da Nang", Decimal("1.0"), Decimal("90000"), 32500),
        ("Thanh Hoa", Decimal("0.5"), Decimal("90000"), 30000),
        ("Can Tho", Decimal("0.5"), Decimal("90000"), 30000),
        ("Can Tho", Decimal("3.0"), Decimal("90000"), 42500),
        ("Ha Noi", Decimal("3.0"), Decimal("150000"), 0),
        ("Da Nang", Decimal("1.0"), Decimal("150000"), 7500),
        (" Ha Noi ", Decimal("3.0"), Decimal("90000"), 22000),
        ("Ha Noi", Decimal("3.0"), Decimal("100000"), 22000),
        ("Da Nang", Decimal("0.6"), Decimal("90000"), 32500),
    ],
    ids=[
        "DFC_001",
        "DFC_002",
        "DFC_003",
        "DFC_004",
        "DFC_005",
        "DFC_005A",
        "DFC_005B",
        "DFC_005C",
        "DFC_006",
        "DFC_007",
        "DFC_011",
        "DFC_012",
        "DFC_013",
    ],
)
def test_calculate_delivery_fee_valid_cases(
    province, weight_kg, order_value, expected_fee
):
    assert calculate_delivery_fee(province, weight_kg, order_value) == expected_fee


@pytest.mark.parametrize(
    ("province", "weight_kg", "order_value"),
    [
        ("", Decimal("1.0"), Decimal("90000")),
        ("   ", Decimal("1.0"), Decimal("90000")),
        ("Hanoi", Decimal("1.0"), Decimal("90000")),
        ("Ha Noi", Decimal("0"), Decimal("90000")),
        ("Ha Noi", Decimal("1.0"), Decimal("-1")),
    ],
    ids=["DFC_008", "DFC_014", "DFC_015", "DFC_009", "DFC_010"],
)
def test_calculate_delivery_fee_invalid_cases(province, weight_kg, order_value):
    with pytest.raises(ValueError):
        calculate_delivery_fee(province, weight_kg, order_value)
