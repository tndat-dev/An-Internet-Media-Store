from decimal import Decimal
from unittest.mock import Mock, patch

import pytest

from apps.orders.models import Order, OrderStatus
from apps.payments.completion_service import PaymentCompletionService
from apps.payments.lifecycle_service import PaymentLifecycleService
from apps.payments.models import (
    PaymentGatewayChoice,
    PaymentStatusChoice,
    PaymentTransaction,
)
from apps.payments.vietqr_service import VietQRSandboxCallbackService


def make_order() -> Order:
    return Order.objects.create(
        total_amount=Decimal("150000.00"),
        status=OrderStatus.PENDING_PAYMENT,
    )


@pytest.mark.django_db
def test_payment_lifecycle_mark_success_merges_provider_payload_and_capture_id():
    order = make_order()
    payment = PaymentTransaction.objects.create(
        order=order,
        gateway=PaymentGatewayChoice.VIETQR,
        amount=Decimal("150000.00"),
        currency="VND",
        status=PaymentStatusChoice.PENDING,
        provider_payload={"provider_metadata": {"content": "VQR123456"}},
    )

    PaymentLifecycleService().mark_success(
        payment,
        capture_id="TXN-123",
        provider_payload_patch={"last_test_callback": {"status": "SUCCESS"}},
    )

    payment.refresh_from_db()
    assert payment.status == PaymentStatusChoice.SUCCESS
    assert payment.capture_id == "TXN-123"
    assert payment.provider_payload["provider_metadata"]["content"] == "VQR123456"
    assert payment.provider_payload["last_test_callback"]["status"] == "SUCCESS"


@pytest.mark.django_db
@patch("apps.payments.completion_service.fulfill_paid_order")
def test_payment_completion_service_marks_success_and_fulfills_order(mock_fulfill):
    order = make_order()
    payment = PaymentTransaction.objects.create(
        order=order,
        gateway=PaymentGatewayChoice.VIETQR,
        amount=Decimal("150000.00"),
        currency="VND",
        status=PaymentStatusChoice.PENDING,
    )

    PaymentCompletionService().complete_successful_payment(
        payment,
        capture_id="TXN-456",
        provider_payload_patch={"last_test_callback": {"status": "SUCCESS"}},
    )

    payment.refresh_from_db()
    assert payment.status == PaymentStatusChoice.SUCCESS
    assert payment.capture_id == "TXN-456"
    assert payment.provider_payload["last_test_callback"]["status"] == "SUCCESS"
    mock_fulfill.assert_called_once_with(str(order.order_id))


@pytest.mark.django_db
def test_vietqr_sandbox_callback_service_delegates_success_to_completion_service(settings):
    settings.VIETQR_ENV = "dev"
    order = make_order()
    payment = PaymentTransaction.objects.create(
        order=order,
        gateway=PaymentGatewayChoice.VIETQR,
        amount=Decimal("150000.00"),
        currency="VND",
        status=PaymentStatusChoice.PENDING,
        transaction_reference="VQR123456",
        transaction_content="VQR123456",
        provider_payload={
            "provider_metadata": {
                "raw_response": {
                    "content": "VQR123456",
                    "amount": "150000",
                    "bankAccount": "0859246671",
                    "bankCode": "MB",
                }
            }
        },
    )
    gateway = Mock()
    gateway.request_test_callback.side_effect = [
        {"success": True, "status": "SUCCESS", "status_code": 200, "variant": "number"},
        {"success": False, "status": "FAILED", "status_code": 400, "variant": "string"},
    ]
    completion_service = Mock()

    result = VietQRSandboxCallbackService(
        gateway=gateway,
        completion_service=completion_service,
    ).request_test_callback(transaction_id=payment.id)

    assert result["success"] is True
    assert result["local_payment_updated"] is True
    completion_service.complete_successful_payment.assert_called_once()
