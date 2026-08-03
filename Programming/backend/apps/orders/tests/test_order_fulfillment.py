from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.carts.models import Cart, CartStatus
from apps.orders.models import Order, OrderStatus
from apps.products.models import Product

from ._helpers import create_product, place_confirmed_order

pytestmark = pytest.mark.django_db


def test_mark_paid_decrements_stock_and_clears_cart():
    product = create_product(stock_quantity=5, barcode="FUL-001")
    cart_token = "ful-decrement-token"
    order_id = place_confirmed_order(product, 2, cart_token)
    client = APIClient()

    response = client.post(f"/api/orders/{order_id}/mark-paid/", {}, format="json")

    assert response.status_code == 200
    assert response.data["status"] == OrderStatus.PENDING_PROCESSING
    product.refresh_from_db()
    assert product.stock_quantity == 3  # 5 - 2
    cart = Cart.objects.get(cart_token=cart_token)
    assert cart.status == CartStatus.CHECKED_OUT
    assert not cart.items.exists()  # cart emptied on fulfillment


def test_mark_paid_is_idempotent_and_does_not_double_decrement():
    product = create_product(stock_quantity=5, barcode="FUL-002")
    cart_token = "ful-idempotent-token"
    order_id = place_confirmed_order(product, 2, cart_token)
    client = APIClient()

    first = client.post(f"/api/orders/{order_id}/mark-paid/", {}, format="json")
    second = client.post(f"/api/orders/{order_id}/mark-paid/", {}, format="json")

    assert first.status_code == 200 and second.status_code == 200
    assert second.data["status"] == OrderStatus.PENDING_PROCESSING
    product.refresh_from_db()
    assert product.stock_quantity == 3  # decremented exactly once


def test_mark_paid_oversell_guard_rolls_back_when_stock_insufficient():
    product = create_product(stock_quantity=5, barcode="FUL-003")
    cart_token = "ful-oversell-token"
    order_id = place_confirmed_order(product, 2, cart_token)
    client = APIClient()

    # Stock drops below the ordered quantity after confirmation (e.g. concurrency).
    Product.objects.filter(product_id=product.product_id).update(stock_quantity=1)

    response = client.post(f"/api/orders/{order_id}/mark-paid/", {}, format="json")

    assert response.status_code == 400
    assert "stock" in str(response.data).lower()
    product.refresh_from_db()
    assert product.stock_quantity == 1  # not decremented (rolled back)
    assert Order.objects.get(order_id=order_id).status == OrderStatus.PENDING_PAYMENT
