from decimal import Decimal

from unittest.mock import patch
from apps.payments.gateways.base import QRCodeResult

import pytest
from rest_framework.test import APIClient

from apps.orders.models import Order, OrderStatus
from apps.payments.gateways.vietqr import VietQRGateway
from apps.payments.models import (
    PaymentGatewayChoice,
    PaymentStatusChoice,
    PaymentTransaction,
)
from apps.payments.vietqr_service import VietQRService

@pytest.fixture(autouse=True)
def mock_vietqr_gateway():
    def fake_create_qr_code(self, *, order_id, amount, payment_id):
        reference = f"AIMS{payment_id}"
        return QRCodeResult(
            transaction_reference=reference,
            qr_payload=f'{{"bankCode":"970436","bankAccount":"1234567890123","amount":"{amount}","description":"{reference}"}}',
            qr_image_url="https://pro.vietqr.vn/qr-generated?token=mock",
            provider_metadata={
                "transaction_id": "TXN_TEST",
                "transaction_reference_id": "VQR_TEST",
            },
        )

    with patch(
        "apps.payments.gateways.vietqr.VietQRGateway.create_qr_code",
        new=fake_create_qr_code,
    ):
        yield

def make_order() -> Order:
    return Order.objects.create(status=OrderStatus.PENDING_PAYMENT)


@pytest.mark.django_db
def test_create_vietqr_payment_generates_pending_qr_transaction():
    order = make_order()
    payment = VietQRService().create_qr_payment(order_id=str(order.order_id), amount=Decimal("150000.00"))

    assert payment.order_id == order.order_id
    assert payment.gateway == PaymentGatewayChoice.VIETQR
    assert payment.status == PaymentStatusChoice.PENDING
    assert payment.amount == Decimal("150000.00")
    assert payment.transaction_reference.startswith("AIMS")
    assert payment.provider_payload["qr_payload"]
    assert payment.provider_payload["qr_image_url"].startswith("https://pro.vietqr.vn/")


@pytest.mark.django_db
def test_qr_code_endpoint_returns_order_amount_reference_and_mock_qr():
    order = make_order()
    client = APIClient()

    response = client.post(
        "/api/payments/vietqr/qr-code/",
        {"order_id": str(order.order_id), "amount": "99000.00"},
        format="json",
    )

    assert response.status_code == 201
    assert response.data["order_id"] == str(order.order_id)
    assert response.data["amount"] == "99000.00"
    assert response.data["payment_method"] == PaymentGatewayChoice.VIETQR
    assert response.data["status"] == "PENDING"
    assert response.data["transaction_reference"].startswith("AIMS")
    assert response.data["qr_payload"]
    assert response.data["qr_image_url"].startswith("https://pro.vietqr.vn/")


@pytest.mark.django_db
def test_status_endpoint_returns_pending_before_callback():
    order = make_order()
    payment = VietQRService().create_qr_payment(order_id=str(order.order_id), amount=Decimal("50000.00"))
    client = APIClient()

    response = client.get(f"/api/payments/{payment.id}/status/")

    assert response.status_code == 200
    assert response.data["transaction_id"] == str(payment.id)
    assert response.data["status"] == "PENDING"


@pytest.mark.django_db
@patch("apps.payments.gateways.vietqr.VietQRGateway.request_test_callback")
def test_status_endpoint_returns_success_after_test_callback(mock_test_callback, settings):
    settings.VIETQR_ENV = "dev"
    order = make_order()
    payment = VietQRService().create_qr_payment(order_id=str(order.order_id), amount=Decimal("50000.00"))
    payment.provider_payload["provider_metadata"] = {
        "raw_response": {
            "content": payment.transaction_reference,
            "amount": "50000",
            "bankAccount": "0859246671",
            "bankCode": "MB",
        }
    }
    payment.save(update_fields=["provider_payload"])
    mock_test_callback.side_effect = [
        {"success": True, "status": "SUCCESS", "status_code": 200, "variant": "number"},
        {"success": False, "status": "FAILED", "status_code": 400, "variant": "string"},
    ]
    client = APIClient()

    callback_response = client.post("/api/payments/vietqr/test-callback/", {"transaction_id": payment.id}, format="json")
    response = client.get(f"/api/payments/{payment.id}/status/")

    assert callback_response.status_code == 200
    assert response.status_code == 200
    assert response.data["status"] == "SUCCESS"
    payment.refresh_from_db()
    assert payment.status == PaymentStatusChoice.SUCCESS


@pytest.mark.django_db
def test_mock_gateway_status_check_does_not_create_or_update_transactions():
    gateway = VietQRGateway()

    status = gateway.check_status(transaction_reference="AIMS-VIETQR-ORDER006")

    assert status == PaymentStatusChoice.PENDING
    assert PaymentTransaction.objects.count() == 0
