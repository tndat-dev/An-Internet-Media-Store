import re
from typing import Any
from django.core.validators import validate_email
from django.core.exceptions import ValidationError as DjangoValidationError

from apps.orders.provinces import VIETNAM_PROVINCE_SET, normalize_province

MAX_NAME_LENGTH = 30
MAX_ADDRESS_LENGTH = 100
MAX_PROVINCE_LENGTH = 100
SUPPORTED_DELIVERY_METHODS = {"STANDARD", "EXPRESS"}

PHONE_PATTERN = re.compile(r"0\d{9}")
SUPPORTED_PHONE_SEPARATORS = (".", "-", "/")


def validate_customer_name(name: str | None) -> bool:
    # customer name is required, max 30 characters, contain letters separated by spaces only
    if name is None:
        return False

    name = name.strip()

    if not name or len(name) > MAX_NAME_LENGTH:
        return False

    parts = name.split()

    return all(part.isalpha() for part in parts)


def validate_phone_number(phone: str | None) -> bool:
    # Phonenumber must contain exactly 10 digits after removing one separator type, must start with 0.

    if phone is None:
        return False

    phone = phone.strip()

    if not phone:
        return False

    if PHONE_PATTERN.fullmatch(phone):
        return True

    used_separators = [sep for sep in SUPPORTED_PHONE_SEPARATORS if sep in phone]

    if len(used_separators) != 1:
        return False

    separator = used_separators[0]
    parts = phone.split(separator)

    if any(part == "" for part in parts):
        return False

    digits_only = "".join(parts)

    return PHONE_PATTERN.fullmatch(digits_only) is not None


def validate_address(address: str | None) -> bool: 
    # Address is required, max 100 characters, allows common simple address characters

    if address is None:
        return False

    address = address.strip()

    if not address or len(address) > MAX_ADDRESS_LENGTH:
        return False

    allowed_special_chars = {" ", "/", ",", ".", "-", "#"}

    for char in address:
        if not (char.isalnum() or char in allowed_special_chars):
            return False

    return True


def validate_email_address(email: str | None) -> bool:
    if email is None:
        return False
    email = email.strip()
    if not email:
        return False
    try:
        validate_email(email)
    except DjangoValidationError:
        return False
    return True


def validate_province(province: str | None) -> bool:
    province = normalize_province(province)
    if not province or len(province) > MAX_PROVINCE_LENGTH:
        return False
    return province in VIETNAM_PROVINCE_SET


def validate_delivery_method(delivery_method: str | None) -> bool:
    if delivery_method is None:
        return True
    return delivery_method.strip().upper() in SUPPORTED_DELIVERY_METHODS


# /*
#  * SOLID Review
#  * Principle: SRP/OCP
#  * Reason: validate_delivery_info coordinates all delivery-field rules and toggles behavior with require_full instead of delegating to field-specific validators.
#  * Impact: Adding optional checkout modes or new delivery fields can make this validator grow and increase regression risk.
#  * Improvement: Compose small field validators or validation rule objects for each delivery scenario.
#  */
def validate_delivery_info(delivery_info: dict[str, Any] | None, require_full: bool = False) -> dict[str, Any]:
    """
    Validate delivery information as 1 small unit.
    Return a readable result instead of raising exceptions, so the caller can show field-level error messages.
    """
    if delivery_info is None:
        delivery_info = {}

    errors = {}

    if not validate_customer_name(delivery_info.get("name")):
        errors["name"] = "INVALID_CUSTOMER_NAME"

    if not validate_phone_number(delivery_info.get("phone")):
        errors["phone"] = "INVALID_PHONE_NUMBER"

    if not validate_address(delivery_info.get("address")):
        errors["address"] = "INVALID_ADDRESS"

    if require_full:
        email = delivery_info.get("email")
        province = delivery_info.get("province")
        delivery_method = delivery_info.get("delivery_method")

        if not validate_email_address(email):
            errors["email"] = "INVALID_EMAIL"
        if not validate_province(province):
            errors["province"] = "INVALID_PROVINCE"
        if not validate_delivery_method(delivery_method):
            errors["deliveryMethod"] = "INVALID_DELIVERY_METHOD"

    return {
        "valid": len(errors) == 0,
        "errors": errors,
    }


class DeliveryInfoValidator:
    """
    Coupling/Cohesion: owns reusable delivery-field rules only. It does not
    calculate fees, mutate orders, or know HTTP serializers.
    """

    @staticmethod
    def validate(delivery_info: dict[str, Any] | None) -> dict[str, Any]:
        return validate_delivery_info(delivery_info, require_full=True)
