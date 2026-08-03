"""
AIMS - Product Price Validator
Deployment path : backend/apps/products/validators.py
"""

from decimal import Decimal, InvalidOperation

# AIMS business rule: current price must stay within [30%, 150%] of original value.
PRICE_RATIO_MIN = Decimal("0.30")
PRICE_RATIO_MAX = Decimal("1.50")


def validate_product_price(
    original_value: Decimal,
    current_price: Decimal,
) -> bool:
    """
    Return True if current_price is within [30%, 150%] of original_value.

    Args:
        original_value: The product's base/original value (excl. VAT).
        current_price:  The product's current selling price (excl. VAT).

    Returns:
        True  -> price is valid per AIMS business rule.
        False -> price is invalid (out of range or bad input).
    """
    # --- None guard ---
    if original_value is None or current_price is None:
        return False

    # --- Type coercion: accept int / float / Decimal ---
    try:
        ov = Decimal(str(original_value))
        cp = Decimal(str(current_price))
    except (InvalidOperation, TypeError, ValueError):
        return False

    # --- Input validity guards (§6A: ov <= 0 or cp < 0) ---
    if ov <= 0:
        return False
    if cp < 0:       # strictly less than: cp=0 falls through to range check
        return False

    # --- Range check ---
    min_price = ov * PRICE_RATIO_MIN
    max_price = ov * PRICE_RATIO_MAX

    return min_price <= cp <= max_price
