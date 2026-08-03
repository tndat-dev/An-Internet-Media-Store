from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.orders.models import Order, OrderStatus
from apps.payments.models import (
    PaymentGatewayChoice,
    PaymentStatusChoice,
    PaymentTransaction,
    RefundStatusChoice,
)

from ._helpers import create_product, make_user_token, place_confirmed_order

pytestmark = pytest.mark.django_db


def _manager_client(username: str = "linh") -> APIClient:
    _, key = make_user_token(username=username, role_name="PRODUCT_MANAGER")
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {key}")
    return client


def _rejected_vietqr_order(barcode: str, cart_token: str) -> str:
    """Place + pay (VietQR) + reject an order, leaving a MANUAL_REQUIRED refund."""
    product = create_product(stock_quantity=5, barcode=barcode)
    order_id = place_confirmed_order(product, 1, cart_token)
    APIClient().post(f"/api/orders/{order_id}/mark-paid/", {}, format="json")
    PaymentTransaction.objects.create(
        order=Order.objects.get(order_id=order_id),
        gateway=PaymentGatewayChoice.VIETQR,
        status=PaymentStatusChoice.SUCCESS,
        amount=Decimal("99000.00"),
        currency="VND",
    )
    _manager_client(username="rejecter").post(
        f"/api/orders/manage/{order_id}/reject/", {"reason": "n/a"}, format="json"
    )
    return order_id


def test_refunds_list_shows_manual_vietqr_orders():
    order_id = _rejected_vietqr_order("REF-001", "ref-list-token")
    client = _manager_client()

    response = client.get("/api/orders/manage/refunds/")

    assert response.status_code == 200
    rows = {o["orderId"]: o for o in response.data["results"]}
    assert order_id in rows
    assert rows[order_id]["status"] == OrderStatus.REJECTED
    assert rows[order_id]["refundSummary"]["refundStatus"] == RefundStatusChoice.MANUAL_REQUIRED


def test_refunds_list_excludes_paypal_auto_refunds():
    """PayPal cancelled/rejected orders are auto-refunded, not manual — hidden here."""
    product = create_product(stock_quantity=5, barcode="REF-002")
    order_id = place_confirmed_order(product, 1, "ref-paypal-token")
    APIClient().post(f"/api/orders/{order_id}/mark-paid/", {}, format="json")
    PaymentTransaction.objects.create(
        order=Order.objects.get(order_id=order_id),
        gateway=PaymentGatewayChoice.PAYPAL,
        status=PaymentStatusChoice.SUCCESS,
        capture_id="CAP-REF-2",
        amount=Decimal("99000.00"),
        currency="USD",
    )
    client = _manager_client()
    client.post(f"/api/orders/manage/{order_id}/reject/", {"reason": "n/a"}, format="json")

    response = client.get("/api/orders/manage/refunds/")

    assert response.status_code == 200
    assert order_id not in [o["orderId"] for o in response.data["results"]]


def test_mark_refunded_completes_manual_refund():
    order_id = _rejected_vietqr_order("REF-003", "ref-mark-token")
    client = _manager_client()

    response = client.post(
        f"/api/orders/manage/{order_id}/mark-refunded/", {"note": "Bank ref 12345"}, format="json"
    )

    assert response.status_code == 200
    summary = response.data["refundSummary"]
    assert summary["refundStatus"] == RefundStatusChoice.SUCCESS
    assert summary["paymentStatus"] == PaymentStatusChoice.REFUNDED
    assert summary["processedBy"] == "linh"
    assert summary["processedAt"] is not None
    assert "Bank ref 12345" in summary["manualRefundNote"]

    payment = PaymentTransaction.objects.get(order_id=order_id, gateway=PaymentGatewayChoice.VIETQR)
    assert payment.status == PaymentStatusChoice.REFUNDED
    refund = payment.refunds.order_by("-created_at").first()
    assert refund.refund_status == RefundStatusChoice.SUCCESS
    assert refund.processed_by is not None


def test_mark_refunded_rejects_order_without_manual_refund():
    """An order with no outstanding manual refund cannot be marked refunded."""
    product = create_product(stock_quantity=5, barcode="REF-004")
    order_id = place_confirmed_order(product, 1, "ref-guard-token")  # no payment, no refund
    client = _manager_client()

    response = client.post(f"/api/orders/manage/{order_id}/mark-refunded/", {}, format="json")

    assert response.status_code == 400


def test_refunds_list_requires_manager_role():
    assert APIClient().get("/api/orders/manage/refunds/").status_code == 401
    _, key = make_user_token(username="nobody", role_name=None)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {key}")
    assert client.get("/api/orders/manage/refunds/").status_code == 403
