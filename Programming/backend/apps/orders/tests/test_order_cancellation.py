from decimal import Decimal

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from apps.orders.models import Order, OrderStatus
from apps.orders.services import can_cancel_order, determine_refund_action
from apps.payments.models import (
    PaymentGatewayChoice,
    PaymentStatusChoice,
    PaymentTransaction,
    RefundStatusChoice,
    RefundTransaction,
)
from apps.payments.refund_service import RefundResponse

from ._helpers import create_product, place_confirmed_order

pytestmark = pytest.mark.django_db


class TestOrderCancellation:

    # OCR_001 – PENDING_PROCESSING => can cancel
    def test_OCR_001_pending_processing_can_cancel(self):
        assert can_cancel_order("PENDING_PROCESSING") == True

    # OCR_002 – APPROVED => cannot cancel
    def test_OCR_002_approved_cannot_cancel(self):
        assert can_cancel_order("APPROVED") == False

    # OCR_003 – REJECTED => cannot cancel
    def test_OCR_003_rejected_cannot_cancel(self):
        assert can_cancel_order("REJECTED") == False

    # OCR_004 – CANCELLED => cannot cancel
    def test_OCR_004_cancelled_cannot_cancel(self):
        assert can_cancel_order("CANCELLED") == False

    # --- determine_refund_action() – Decision Table ---

    # OCR_005 – PENDING + PAYPAL => AUTO_REFUND
    def test_OCR_005_pending_paypal_auto_refund(self):
        assert determine_refund_action("PENDING_PROCESSING", "PAYPAL") == "AUTO_REFUND"

    # OCR_006 – PENDING + VIETQR => MANUAL_REFUND_REQUIRED
    def test_OCR_006_pending_vietqr_manual_refund(self):
        assert determine_refund_action("PENDING_PROCESSING", "VIETQR") == "MANUAL_REFUND_REQUIRED"

    # OCR_007 – APPROVED + PAYPAL => NOT_REFUNDABLE_BY_CUSTOMER_CANCEL
    def test_OCR_007_approved_paypal_not_refundable(self):
        assert determine_refund_action("APPROVED", "PAYPAL") == "NOT_REFUNDABLE_BY_CUSTOMER_CANCEL"

    # OCR_008 – invalid status => INVALID_ORDER_STATUS
    def test_OCR_008_invalid_status(self):
        assert determine_refund_action("INVALID_STATUS", "PAYPAL") == "INVALID_ORDER_STATUS"

    # OCR_009 – invalid payment method => INVALID_PAYMENT_METHOD
    def test_OCR_009_invalid_payment_method(self):
        assert determine_refund_action("PENDING_PROCESSING", "CASH") == "INVALID_PAYMENT_METHOD"


def _paid_paypal_order(product, quantity: int, cart_token: str):
    order_id = place_confirmed_order(product, quantity, cart_token)
    APIClient().post(f"/api/orders/{order_id}/mark-paid/", {}, format="json")
    order = Order.objects.get(order_id=order_id)
    payment = PaymentTransaction.objects.create(
        order=order,
        gateway=PaymentGatewayChoice.PAYPAL,
        status=PaymentStatusChoice.SUCCESS,
        capture_id=f"CAP-{cart_token}",
        amount=Decimal("198000.00"),
        currency="VND",
        provider_payload={
            "paypal_amount": "7.77",
            "paypal_currency": "USD",
            "source_amount_vnd": "198000.00",
        },
    )
    return order, payment


@override_settings(PAYPAL_CLIENT_ID="", PAYPAL_CLIENT_SECRET="")
def test_customer_cancel_paypal_order_refunds_automatically():
    product = create_product(stock_quantity=4, barcode="CAN-REFUND-001")
    order, payment = _paid_paypal_order(product, 2, "cancel-paypal-token")

    response = APIClient().post(f"/api/orders/{order.cancel_token}/cancel/", {}, format="json")

    assert response.status_code == 200
    assert response.data["status"] == OrderStatus.CANCELLED
    assert response.data["refundSummary"]["paymentMethod"] == PaymentGatewayChoice.PAYPAL
    assert response.data["refundSummary"]["paymentStatus"] == PaymentStatusChoice.REFUNDED
    assert response.data["refundSummary"]["refundStatus"] == RefundStatusChoice.SUCCESS
    payment.refresh_from_db()
    assert payment.status == PaymentStatusChoice.REFUNDED
    assert payment.refund_id.startswith("MOCK-REF-")
    refund = RefundTransaction.objects.get(payment_transaction=payment)
    assert refund.refund_status == RefundStatusChoice.SUCCESS
    assert refund.refund_amount == Decimal("198000.00")
    product.refresh_from_db()
    assert product.stock_quantity == 4


def test_customer_cancel_paypal_order_blocks_when_refund_fails(monkeypatch):
    product = create_product(stock_quantity=4, barcode="CAN-REFUND-FAIL")
    order, payment = _paid_paypal_order(product, 2, "cancel-paypal-fail-token")

    def fail_refund(*args, **kwargs):
        return RefundResponse(success=False, error_message="PayPal outage")

    monkeypatch.setattr("apps.payments.refund_service.RefundService.refund_order", fail_refund)

    response = APIClient().post(f"/api/orders/{order.cancel_token}/cancel/", {}, format="json")

    assert response.status_code == 400
    assert "refund" in response.data
    order.refresh_from_db()
    assert order.status == OrderStatus.PENDING_PROCESSING
    payment.refresh_from_db()
    assert payment.status == PaymentStatusChoice.SUCCESS
    assert RefundTransaction.objects.filter(payment_transaction=payment).count() == 0
    product.refresh_from_db()
    assert product.stock_quantity == 2
