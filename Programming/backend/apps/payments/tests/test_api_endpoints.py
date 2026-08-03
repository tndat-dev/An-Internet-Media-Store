import base64
from decimal import Decimal
from unittest.mock import Mock, patch

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.orders.models import Order, OrderStatus
from apps.payments.models import (
    PaymentGatewayChoice,
    PaymentStatusChoice,
    PaymentTransaction,
)
from apps.payments.services import CapturePaymentResponse


def make_order() -> Order:
    return Order.objects.create(
        total_amount=Decimal("150000.00"),
        status=OrderStatus.PENDING_PAYMENT,
    )


@pytest.mark.django_db
@patch("apps.payments.views._get_payment_service")
def test_paypal_capture_existing_transaction_uses_completion_lifecycle(mock_get_payment_service):
    order = make_order()
    payment = PaymentTransaction.objects.create(
        order=order,
        gateway=PaymentGatewayChoice.PAYPAL,
        provider_order_id="PP-ORDER-1",
        amount=Decimal("150000.00"),
        currency="VND",
        status=PaymentStatusChoice.PENDING,
        provider_payload={
            "paypal_amount": "6.00",
            "source_amount_vnd": "150000.00",
        },
    )
    service = Mock()
    service.capture_payment.return_value = CapturePaymentResponse(
        success=True,
        transaction_id="CAPTURE-1",
        captured_amount=6.25,
    )
    mock_get_payment_service.return_value = service
    client = APIClient()

    response = client.post(
        "/api/payments/paypal/capture/",
        data={
            "provider_order_id": "PP-ORDER-1",
            "internal_order_id": str(order.order_id),
        },
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    payment.refresh_from_db()
    order.refresh_from_db()
    assert payment.id == response.data["id"]
    assert payment.status == PaymentStatusChoice.SUCCESS
    assert payment.capture_id == "CAPTURE-1"
    assert payment.provider_payload["paypal_captured_amount"] == "6.25"
    assert payment.provider_payload["paypal_currency"] == "USD"
    assert payment.provider_payload["source_amount_vnd"] == "150000.00"
    assert order.status == OrderStatus.PENDING_PROCESSING


@pytest.mark.django_db
@patch("apps.payments.views._get_payment_service")
def test_paypal_capture_fallback_transaction_still_completes_via_lifecycle(mock_get_payment_service):
    order = make_order()
    service = Mock()
    service.capture_payment.return_value = CapturePaymentResponse(
        success=True,
        transaction_id="CAPTURE-2",
        captured_amount=6.75,
    )
    mock_get_payment_service.return_value = service
    client = APIClient()

    response = client.post(
        "/api/payments/paypal/capture/",
        data={
            "provider_order_id": "PP-ORDER-2",
            "internal_order_id": str(order.order_id),
        },
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    payment = PaymentTransaction.objects.get(order=order, gateway=PaymentGatewayChoice.PAYPAL)
    order.refresh_from_db()
    assert payment.id == response.data["id"]
    assert payment.provider_order_id == "PP-ORDER-2"
    assert payment.status == PaymentStatusChoice.SUCCESS
    assert payment.capture_id == "CAPTURE-2"
    assert payment.provider_payload["paypal_captured_amount"] == "6.75"
    assert payment.provider_payload["paypal_currency"] == "USD"
    assert payment.provider_payload["source_amount_vnd"] == "150000.00"
    assert order.status == OrderStatus.PENDING_PROCESSING


@pytest.mark.django_db
def test_token_generate_requires_basic_auth():
    client = APIClient()

    response = client.post("/api/payments/vietqr/token-generate/")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert "Authorization" in response.data or "error" in response.data


@pytest.mark.django_db
def test_legacy_token_generate_no_slash_requires_basic_auth():
    """Legacy token endpoint without trailing slash must not trigger APPEND_SLASH redirect logic."""
    client = APIClient()

    response = client.post("/api/payments/vietqr/api/token_generate")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert "Authorization" in response.data or "error" in response.data


@pytest.mark.django_db
@patch("django.conf.settings.VIETQR_CALLBACK_USERNAME", "test-user")
@patch("django.conf.settings.VIETQR_CALLBACK_PASSWORD", "test-pass")
def test_token_generate_accepts_registered_noslash_path():
    client = APIClient()
    credentials = base64.b64encode(b"test-user:test-pass").decode()

    response = client.post(
        "/api/payments/vietqr/api/token_generate",
        HTTP_AUTHORIZATION=f"Basic {credentials}",
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.data["token_type"] == "Bearer"
    assert "access_token" in response.data


@pytest.mark.django_db
@patch("django.conf.settings.VIETQR_CALLBACK_USERNAME", "test-user")
@patch("django.conf.settings.VIETQR_CALLBACK_PASSWORD", "test-pass")
def test_legacy_token_generate_no_slash_with_correct_credentials(settings):
    """Legacy token endpoint without trailing slash must behave like the canonical endpoint."""
    client = APIClient()
    credentials = base64.b64encode(b"test-user:test-pass").decode()

    response = client.post(
        "/api/payments/vietqr/api/token_generate",
        HTTP_AUTHORIZATION=f"Basic {credentials}",
    )

    assert response.status_code == status.HTTP_200_OK
    assert "access_token" in response.data
    assert response.data["token_type"] == "Bearer"
    assert "expires_in" in response.data


@pytest.mark.django_db
def test_token_generate_rejects_incorrect_credentials():
    """Test token endpoint rejects wrong Basic Auth credentials."""
    client = APIClient()
    credentials = base64.b64encode(b"test-user:test-pass").decode()

    response = client.post(
        "/api/payments/vietqr/api/token_generate/",
        HTTP_AUTHORIZATION=f"Basic {credentials}",
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.data["token_type"] == "Bearer"
    assert "access_token" in response.data


@pytest.mark.django_db
def test_token_generate_rejects_incorrect_credentials():
    client = APIClient()
    credentials = base64.b64encode(b"wrong-user:wrong-pass").decode()

    response = client.post(
        "/api/payments/vietqr/api/token_generate",
        HTTP_AUTHORIZATION=f"Basic {credentials}",
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_legacy_transaction_sync_no_slash_requires_no_redirect():
    """Legacy transaction-sync endpoint without trailing slash must reach the view directly."""
    client = APIClient()

    response = client.post(
        "/api/payments/vietqr/bank/api/transaction-sync",
        data={"content": "VQR123456", "amount": "150000"},
        content_type="application/json",
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.data["error"] is True
    assert "errorReason" in response.data
    assert "toastMessage" in response.data
    assert "reftransactionid" in response.data["object"]


@pytest.mark.django_db
def test_test_callback_rejects_non_dev_environment(settings):
    settings.VIETQR_ENV = "prod"
    client = APIClient()

    response = client.post(
        "/api/payments/vietqr/test-callback/",
        data={"transaction_id": 1},
        content_type="application/json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
@patch("apps.payments.gateways.vietqr.VietQRGateway.request_test_callback")
def test_test_callback_provider_failure_leaves_payment_pending(mock_test_callback, settings):
    settings.VIETQR_ENV = "dev"
    order = make_order()
    payment = PaymentTransaction.objects.create(
        order=order,
        amount=Decimal("150000.00"),
        status=PaymentStatusChoice.PENDING,
        transaction_reference="VQR123456 AIMS1",
        gateway=PaymentGatewayChoice.VIETQR,
        provider_payload={
            "provider_metadata": {
                "raw_response": {
                    "content": "VQR123456 AIMS1",
                    "amount": "150000",
                    "bankAccount": "0859246671",
                    "bankCode": "MB",
                    "orderId": "AIMS1",
                    "transactionId": "",
                    "transactionRefId": "REF123",
                    "existing": 0,
                }
            }
        },
    )
    mock_test_callback.return_value = {
        "success": False,
        "sandbox_only": True,
        "status_code": 400,
        "details": {"status": "FAILED", "message": "E05"},
    }
    client = APIClient()

    response = client.post(
        "/api/payments/vietqr/test-callback/",
        data={"transaction_id": payment.id},
        content_type="application/json",
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.data["success"] is False
    assert response.data["local_payment_updated"] is False
    assert response.data["status"] == "FAILED"

    payment.refresh_from_db()
    order.refresh_from_db()
    assert payment.status == PaymentStatusChoice.PENDING
    assert order.status == OrderStatus.PENDING_PAYMENT


@pytest.mark.django_db
@patch("apps.payments.views.VietQRTransactionSyncView._verify_callback_token")
def test_transaction_sync_acknowledges_valid_token_without_mutating_payment(mock_verify):
    mock_verify.return_value = True
    order = make_order()
    payment = PaymentTransaction.objects.create(
        order=order,
        amount=Decimal("150000.00"),
        status=PaymentStatusChoice.PENDING,
        transaction_reference="VQR123456",
        gateway=PaymentGatewayChoice.VIETQR,
    )
    client = APIClient()

    response = client.post(
        "/api/payments/vietqr/bank/api/transaction-sync",
        data={
            "content": "VQR123456",
            "amount": "150000",
            "transactionId": "TXN12345",
            "successFlag": True,
        },
        content_type="application/json",
        HTTP_AUTHORIZATION="Bearer valid_token",
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.data["error"] is False
    assert response.data["toastMessage"] == "Callback received successfully"
    assert response.data["object"]["reftransactionid"] == "TXN12345"

    payment.refresh_from_db()
    order.refresh_from_db()
    assert payment.status == PaymentStatusChoice.PENDING
    assert order.status == OrderStatus.PENDING_PAYMENT


@pytest.mark.django_db
@patch("apps.payments.views.VietQRTransactionSyncView._verify_callback_token")
def test_legacy_transaction_sync_no_slash_with_valid_token(mock_verify):
    """Legacy transaction-sync endpoint without trailing slash must behave like the canonical endpoint."""
    mock_verify.return_value = True
    order = make_order()
    payment = PaymentTransaction.objects.create(
        order=order,
        amount=Decimal("150000.00"),
        status=PaymentStatusChoice.PENDING,
        transaction_reference="VQR123456",
        gateway=PaymentGatewayChoice.VIETQR,
    )

    client = APIClient()

    response = client.post(
        "/api/payments/vietqr/bank/api/transaction-sync",
        data={
            "orderId": "AIMS1",
            "content": "VQR123456",
            "bankAccount": "0859246671",
            "amount": "150000",
            "transactionDate": "2026-05-29 10:30:45",
            "transactionId": "TXN12345",
            "referenceNumber": "REF123",
            "transType": "C",
            "description": "Payment",
            "successFlag": True,
        },
        content_type="application/json",
        HTTP_AUTHORIZATION="Bearer valid_token",
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.data["error"] is False
    assert response.data["errorReason"] is None
    assert response.data["toastMessage"] == "Transaction processed successfully"
    assert response.data["object"]["reftransactionid"] == "TXN12345"

    payment.refresh_from_db()
    assert payment.status == PaymentStatusChoice.SUCCESS


@pytest.mark.django_db
@patch("apps.payments.views.VietQRTransactionSyncView._verify_callback_token")
def test_transaction_sync_with_invalid_token(mock_verify):
    """Test transaction-sync endpoint rejects invalid Bearer token."""
    mock_verify.return_value = False
    client = APIClient()

    response = client.post(
        "/api/payments/vietqr/bank/api/transaction-sync/",
        data={},
        content_type="application/json",
        HTTP_AUTHORIZATION="Bearer invalid_token",
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.data["error"] is True
    assert response.data["errorReason"] == "Invalid Bearer token"


@pytest.mark.django_db
def test_transaction_sync_acknowledges_missing_token_for_sandbox_connectivity():
    client = APIClient()

    response = client.post(
        "/api/payments/vietqr/bank/api/transaction-sync/",
        data={"transactionid": "REF-NOAUTH"},
        content_type="application/json",
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.data["error"] is False
    assert response.data["object"]["reftransactionid"] == "REF-NOAUTH"
