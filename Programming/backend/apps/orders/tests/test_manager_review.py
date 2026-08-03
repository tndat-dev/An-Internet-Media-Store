from decimal import Decimal

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from apps.orders.models import Order, OrderStatus
from apps.payments.models import PaymentGatewayChoice, PaymentStatusChoice, PaymentTransaction, RefundStatusChoice

from ._helpers import create_product, make_user_token, place_confirmed_order

pytestmark = pytest.mark.django_db


def _paid_order(product, qty, cart_token) -> str:
    """Place + pay an order so it is PENDING_PROCESSING (manager review queue)."""
    order_id = place_confirmed_order(product, qty, cart_token)
    APIClient().post(f"/api/orders/{order_id}/mark-paid/", {}, format="json")
    return order_id


def _manager_client() -> APIClient:
    _, key = make_user_token(username="linh", role_name="PRODUCT_MANAGER")
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {key}")
    return client


def test_pending_list_requires_manager_role():
    create_product(barcode="MGR-000")
    # No token -> not authenticated -> 401 (auth challenge present).
    assert APIClient().get("/api/orders/manage/pending/").status_code == 401
    # Authenticated token but no PRODUCT_MANAGER role -> 403 (forbidden).
    _, key = make_user_token(username="nobody", role_name=None)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {key}")
    assert client.get("/api/orders/manage/pending/").status_code == 403


def test_manager_pending_list_returns_pending_processing_orders():
    product = create_product(stock_quantity=5, barcode="MGR-001")
    order_id = _paid_order(product, 1, "mgr-pending-token")
    client = _manager_client()

    response = client.get("/api/orders/manage/pending/")

    assert response.status_code == 200
    ids = [o["orderId"] for o in response.data["results"]]
    assert order_id in ids


def test_manager_approve_sets_approved_and_processor():
    product = create_product(stock_quantity=5, barcode="MGR-002")
    order_id = _paid_order(product, 1, "mgr-approve-token")
    client = _manager_client()

    response = client.post(f"/api/orders/manage/{order_id}/approve/", {}, format="json")

    assert response.status_code == 200
    assert response.data["status"] == OrderStatus.APPROVED
    order = Order.objects.get(order_id=order_id)
    assert order.processed_by is not None
    assert order.processed_at is not None
    product.refresh_from_db()
    assert product.stock_quantity == 4  # approve does NOT change stock


@override_settings(PAYPAL_CLIENT_ID="", PAYPAL_CLIENT_SECRET="")  # force mock gateway
def test_manager_reject_restores_stock_and_records_refund():
    product = create_product(stock_quantity=5, barcode="MGR-003")
    order_id = _paid_order(product, 2, "mgr-reject-token")
    PaymentTransaction.objects.create(
        order=Order.objects.get(order_id=order_id),
        gateway=PaymentGatewayChoice.PAYPAL,
        status=PaymentStatusChoice.SUCCESS,
        capture_id="CAP-9",
        amount=Decimal("198000.00"),
        currency="VND",
        provider_payload={
            "paypal_amount": "7.92",
            "paypal_currency": "USD",
            "source_amount_vnd": "198000.00",
        },
    )
    client = _manager_client()

    response = client.post(f"/api/orders/manage/{order_id}/reject/", {"reason": "Out of stock"}, format="json")

    assert response.status_code == 200
    assert response.data["status"] == OrderStatus.REJECTED
    assert response.data["refundSummary"]["paymentStatus"] == PaymentStatusChoice.REFUNDED
    assert response.data["refundSummary"]["refundStatus"] == RefundStatusChoice.SUCCESS
    product.refresh_from_db()
    assert product.stock_quantity == 5  # restored (3 -> 5)
    payment = PaymentTransaction.objects.get(capture_id="CAP-9")
    assert payment.status == PaymentStatusChoice.REFUNDED
    refund = payment.refunds.get(refund_status=RefundStatusChoice.SUCCESS)
    assert refund.refund_amount == Decimal("198000.00")
    order = Order.objects.get(order_id=order_id)
    assert order.processed_by is not None


def test_manager_cannot_approve_non_pending_order():
    product = create_product(stock_quantity=5, barcode="MGR-004")
    order_id = place_confirmed_order(product, 1, "mgr-guard-token")  # still PENDING_PAYMENT
    client = _manager_client()

    response = client.post(f"/api/orders/manage/{order_id}/approve/", {}, format="json")

    assert response.status_code == 400
