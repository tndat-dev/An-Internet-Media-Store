"""Unit tests for DeletionPolicy in isolation.

These exist to demonstrate the SRP win: the deletion rules (per-request cap,
per-manager daily cap, delete-vs-deactivate) are now testable without driving the
whole ProductService.delete_products flow.
"""

import pytest
from django.core.exceptions import ValidationError

from apps.products.models import (
    Product,
    ProductHistory,
    ProductHistoryActionType,
    ProductStatus,
    ProductType,
)
from apps.products.policies import DeletionPolicy
from apps.users.models import User


def _product(stock: int) -> Product:
    return Product(
        product_type=ProductType.BOOK,
        title="t",
        category="c",
        height=1,
        width=1,
        length=1,
        weight=1,
        barcode="DP-X",
        original_value="100.00",
        current_price="100.00",
        stock_quantity=stock,
    )


def test_check_request_size_allows_up_to_max():
    DeletionPolicy().check_request_size(DeletionPolicy.MAX_PER_REQUEST)  # no raise


def test_check_request_size_rejects_over_max():
    with pytest.raises(ValidationError):
        DeletionPolicy().check_request_size(DeletionPolicy.MAX_PER_REQUEST + 1)


def test_resolve_status_zero_stock_deletes():
    status, action = DeletionPolicy().resolve_status(_product(0))
    assert status == ProductStatus.DELETED
    assert action == ProductHistoryActionType.DELETE


def test_resolve_status_with_stock_deactivates():
    status, action = DeletionPolicy().resolve_status(_product(5))
    assert status == ProductStatus.DEACTIVATED
    assert action == ProductHistoryActionType.DEACTIVATE


@pytest.mark.django_db
def test_check_daily_cap_rejects_when_quota_reached():
    manager = User.objects.create(username="dp-mgr", email="dp-mgr@aims.local")
    product = _product(0)
    product.save()
    for _ in range(DeletionPolicy.MAX_PER_DAY):
        ProductHistory.objects.create(
            product=product,
            action_type=ProductHistoryActionType.DELETE,
            performed_by=manager,
        )
    with pytest.raises(ValidationError):
        DeletionPolicy().check_daily_cap(manager_id="dp-mgr", adding=1)


@pytest.mark.django_db
def test_check_daily_cap_allows_within_quota():
    User.objects.create(username="dp-mgr2", email="dp-mgr2@aims.local")
    DeletionPolicy().check_daily_cap(manager_id="dp-mgr2", adding=5)  # no history -> ok
