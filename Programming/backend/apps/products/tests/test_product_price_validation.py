"""
AIMS - Unit Test: Product Price Validation (Lean Suite)
Deployment path : backend/apps/products/tests/test_product_price_validation.py
"""

import pytest
from decimal import Decimal

from apps.products.validators import validate_product_price
from apps.products.tests.conftest import register_meta

_PPV_SUITE = [
    # --- 1. VÙNG TƯƠNG ĐƯƠNG (Equivalence Partitioning) ---
    ("PPV_001", "EP: Current price within valid range (50% of original)", Decimal("100000"), Decimal("50000"),  True),
    ("PPV_002", "EP: Current price is too low (20% of original)",        Decimal("100000"), Decimal("20000"),  False),
    ("PPV_003", "EP: Current price is too high (200% of original)",       Decimal("100000"), Decimal("200000"), False),
    
    # --- 2. GIÁ TRỊ BIÊN (Boundary Value Analysis) ---
    ("PPV_004", "BVA: Current price is just below 30% (29,999)",         Decimal("100000"), Decimal("29999"),  False),
    ("PPV_005", "BVA: Current price is exactly 30% boundary",            Decimal("100000"), Decimal("30000"),  True),
    ("PPV_006", "BVA: Current price is just above 30% (30,001)",         Decimal("100000"), Decimal("30001"),  True),
    ("PPV_007", "BVA: Current price is just below 150% (149,999)",       Decimal("100000"), Decimal("149999"), True),
    ("PPV_008", "BVA: Current price is exactly 150% boundary",           Decimal("100000"), Decimal("150000"), True),
    ("PPV_009", "BVA: Current price is just above 150% (150,001)",        Decimal("100000"), Decimal("150001"), False),
    
    # --- 3. ĐIỀU KIỆN CHẶN LỖI SỐ HỌC (Guard Clauses) ---
    ("PPV_010", "Guard: Original value is 0",                            Decimal("0"),       Decimal("10000"), False),
    ("PPV_011", "Guard: Original value is negative (< 0)",              Decimal("-100000"), Decimal("50000"), False),
    ("PPV_012", "Guard: Current price is negative (< 0)",               Decimal("100000"),  Decimal("-1"),    False),
    
    # --- 4. NGOẠI LỆ HỆ THỐNG & ĐỘ LỚN (Edge Cases / Stress) ---
    ("PPV_013", "Edge: Original value is None",                          None,              Decimal("50000"), False),
    ("PPV_014", "Edge: Current price is None",                           Decimal("100000"), None,             False),
    ("PPV_015", "Edge: Massive scale value stress test (50,000,000)",    Decimal("50000000"), Decimal("50000000"), True),
]

# Tự động đăng ký metadata để phục vụ in bảng biểu
for _id, _desc, _ov, _cp, _exp in _PPV_SUITE:
    register_meta(_id, _desc, _exp)


@pytest.mark.parametrize("tc_id, description, original_value, current_price, expected",
    _PPV_SUITE, ids=[r[0] for r in _PPV_SUITE])
def test_product_price_validation(tc_id, description, original_value, current_price, expected):
    """
    Unified Test Runner for Product Price Validation.
    Executes a lean, non-redundant suite with exact PPV_xxx sequential codes.
    """
    assert validate_product_price(original_value, current_price) is expected