from decimal import Decimal

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from apps.orders.models import Order, OrderStatus
from apps.payments.models import (
    PaymentGatewayChoice,
    PaymentStatusChoice,
    PaymentTransaction,
    RefundMethodChoice,
    RefundStatusChoice,
    RefundTransaction,
)

from ._helpers import create_product, place_confirmed_order

pytestmark = pytest.mark.django_db


def _pay(order_id: str, gateway: str, **overrides) -> PaymentTransaction:
    order = Order.objects.get(order_id=order_id)
    data = {
        "order": order,
        "gateway": gateway,
        "status": PaymentStatusChoice.SUCCESS,
        "capture_id": "CAP-1",
        "amount": Decimal("198000.00"),
        "currency": "VND",
    }
    if gateway == PaymentGatewayChoice.PAYPAL:
        data["provider_payload"] = {
            "paypal_amount": "7.92",
            "paypal_currency": "USD",
            "source_amount_vnd": "198000.00",
        }
    data.update(overrides)
    return PaymentTransaction.objects.create(**data)


def _fulfill_and_pay(product, qty, cart_token, gateway):
    order_id = place_confirmed_order(product, qty, cart_token)
    APIClient().post(f"/api/orders/{order_id}/mark-paid/", {}, format="json")
    tx = _pay(order_id, gateway)
    return order_id, tx


@override_settings(PAYPAL_CLIENT_ID="", PAYPAL_CLIENT_SECRET="")  # force mock gateway
def test_cancel_paypal_order_refunds_and_restores_stock():
    product = create_product(stock_quantity=5, barcode="CAN-001")
    order_id, tx = _fulfill_and_pay(product, 2, "cancel-paypal-token", PaymentGatewayChoice.PAYPAL)
    cancel_token = Order.objects.get(order_id=order_id).cancel_token
    client = APIClient()

    response = client.post(f"/api/orders/{cancel_token}/cancel/", {}, format="json")

    assert response.status_code == 200
    assert response.data["status"] == OrderStatus.CANCELLED
    product.refresh_from_db()
    assert product.stock_quantity == 5  # restored (3 -> 5)
    tx.refresh_from_db()
    assert tx.status == PaymentStatusChoice.REFUNDED
    refund = RefundTransaction.objects.get(payment_transaction=tx)
    assert refund.refund_method == RefundMethodChoice.PAYPAL_API
    assert refund.refund_status == RefundStatusChoice.SUCCESS


def test_cancel_vietqr_order_flags_manual_refund():
    product = create_product(stock_quantity=5, barcode="CAN-002")
    order_id, tx = _fulfill_and_pay(product, 1, "cancel-vietqr-token", PaymentGatewayChoice.VIETQR)
    cancel_token = Order.objects.get(order_id=order_id).cancel_token
    client = APIClient()

    response = client.post(f"/api/orders/{cancel_token}/cancel/", {}, format="json")

    assert response.status_code == 200
    assert response.data["status"] == OrderStatus.CANCELLED
    product.refresh_from_db()
    assert product.stock_quantity == 5  # restored (4 -> 5)
    refund = RefundTransaction.objects.get(payment_transaction=tx)
    assert refund.refund_method == RefundMethodChoice.MANUAL_BANK_TRANSFER
    assert refund.refund_status == RefundStatusChoice.MANUAL_REQUIRED
    assert refund.manual_refund_note  # required by CHECK constraint


def test_cannot_cancel_unpaid_order():
    product = create_product(stock_quantity=5, barcode="CAN-003")
    order_id = place_confirmed_order(product, 1, "cancel-unpaid-token")  # still PENDING_PAYMENT
    cancel_token = Order.objects.get(order_id=order_id).cancel_token
    client = APIClient()

    response = client.post(f"/api/orders/{cancel_token}/cancel/", {}, format="json")

    assert response.status_code == 400
    assert Order.objects.get(order_id=order_id).status == OrderStatus.PENDING_PAYMENT
