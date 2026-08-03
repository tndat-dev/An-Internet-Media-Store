"""Unit tests for the product-subtype Strategy + Registry.

These pin the OCP seam: every ProductType must have a registered strategy whose
behaviour matches the pre-refactor config (related names, required fields, enum
normalization), and an unknown type must fail as a validation error, not a 500.
"""

import pytest
from django.core.exceptions import ValidationError

from apps.products.models import ProductType
from apps.products.types import ProductTypeRegistry


def test_every_product_type_has_a_registered_strategy():
    # Parity / "did you forget to register" safety net for new types.
    for value in ProductType.values:
        strategy = ProductTypeRegistry.get(value)
        assert strategy.product_type == value
        assert strategy.model is not None
        assert strategy.related_name


def test_related_names_match_reverse_accessors():
    assert set(ProductTypeRegistry.related_names()) == {
        "book_details",
        "cd_details",
        "dvd_details",
        "newspaper_details",
    }


def test_get_unknown_type_raises_validation_error():
    with pytest.raises(ValidationError):
        ProductTypeRegistry.get("VINYL")


def test_required_fields_missing_are_reported():
    book = ProductTypeRegistry.get(ProductType.BOOK)
    missing = book.validate_required({"authors": "x"}, require_all=True)
    assert set(missing) == {"cover_type", "publisher", "publication_date"}


def test_required_fields_partial_update_only_rejects_blank_provided():
    book = ProductTypeRegistry.get(ProductType.BOOK)
    # Same-type partial edit: absent fields are fine, only an explicitly blank one is rejected.
    assert book.validate_required({"authors": "x"}, require_all=False) == []
    assert book.validate_required({"authors": "  "}, require_all=False) == ["authors"]


def test_dvd_enum_normalization_canonicalizes_value():
    dvd = ProductTypeRegistry.get(ProductType.DVD)
    details = {"disc_type": "blu ray"}
    assert dvd.normalize_enums(details) == []
    assert details["disc_type"] == "Blu-ray"


def test_book_enum_rejects_unknown_value():
    book = ProductTypeRegistry.get(ProductType.BOOK)
    errors = book.normalize_enums({"cover_type": "Leather"})
    assert errors and "cover_type" in errors[0]
