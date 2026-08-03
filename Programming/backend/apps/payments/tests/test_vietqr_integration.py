from decimal import Decimal
from unittest.mock import Mock, call, patch

import pytest
from django.core.exceptions import ValidationError

from apps.orders.models import Order, OrderStatus
from apps.payments.models import (
    PaymentGatewayChoice,
    PaymentStatusChoice,
    PaymentTransaction,
)
from apps.payments.vietqr_service import VietQRSandboxCallbackService, VietQRService


def make_order() -> Order:
    return Order.objects.create(
        total_amount=Decimal("150000.00"),
        status=OrderStatus.PENDING_PAYMENT,
    )


def create_vietqr_payment(
    *,
    order: Order,
    amount: Decimal = Decimal("150000.00"),
    status: str = PaymentStatusChoice.PENDING,
    reference: str = "VQR123456",
) -> PaymentTransaction:
    return PaymentTransaction.objects.create(
        order=order,
        amount=amount,
        status=status,
        transaction_reference=reference,
        transaction_content=reference,
        gateway=PaymentGatewayChoice.VIETQR,
    )


@pytest.mark.django_db
@patch("apps.payments.gateways.vietqr.VietQRTokenManager")
@patch("apps.payments.gateways.vietqr.requests.post")
def test_create_qr_payment_creates_pending_transaction(mock_post, mock_token_manager):
    order = make_order()
    mock_token_instance = Mock()
    mock_token_instance.get_token.return_value = "token_abc"
    mock_token_manager.return_value = mock_token_instance

    mock_post.return_value.json.return_value = {
        "qrCode": "0002010102123857VQR123456",
        "qrLink": "https://pro.vietqr.vn/qr-generated?token=abc",
        "content": "VQR123456",
        "transactionRefId": "REF123",
        "transactionId": "TXN12345",
        "bankCode": "MB",
        "bankAccount": "0859246671",
        "userBankName": "Chu Tuan Linh",
        "amount": "150000",
        "orderId": "AIMS1",
    }

    payment = VietQRService().create_qr_payment(
        order_id=str(order.order_id),
        amount=Decimal("150000.00"),
    )

    assert payment.status == PaymentStatusChoice.PENDING
    assert payment.transaction_reference == "VQR123456"
    assert payment.provider_payload["provider_metadata"]["transaction_id"] == "TXN12345"
    assert PaymentTransaction.objects.get(id=payment.id).status == PaymentStatusChoice.PENDING


@pytest.mark.django_db
def test_create_qr_payment_validates_order_id():
    with pytest.raises(ValidationError) as exc:
        VietQRService().create_qr_payment(order_id="", amount=Decimal("150000.00"))

    assert "order_id" in str(exc.value)


@pytest.mark.django_db
def test_create_qr_payment_validates_amount():
    order = make_order()

    with pytest.raises(ValidationError) as exc:
        VietQRService().create_qr_payment(order_id=str(order.order_id), amount=Decimal("0"))

    assert "amount" in str(exc.value)


@pytest.mark.django_db
@patch("apps.payments.gateways.vietqr.VietQRTokenManager")
@patch("apps.payments.gateways.vietqr.requests.post")
def test_create_qr_payment_fails_gracefully(mock_post, mock_token_manager):
    order = make_order()
    mock_token_instance = Mock()
    mock_token_instance.get_token.return_value = "token_abc"
    mock_token_manager.return_value = mock_token_instance
    mock_post.side_effect = Exception("VietQR API error")

    with pytest.raises(Exception):
        VietQRService().create_qr_payment(
            order_id=str(order.order_id),
            amount=Decimal("150000.00"),
        )

    payment = PaymentTransaction.objects.get(order=order)
    assert payment.status == PaymentStatusChoice.FAILED
    assert "error" in payment.provider_payload


@pytest.mark.django_db
@patch("apps.payments.gateways.vietqr.VietQRGateway.request_test_callback")
def test_request_test_callback_uses_generated_qr_content(mock_test_callback, settings):
    settings.VIETQR_ENV = "dev"
    order = make_order()
    payment = create_vietqr_payment(order=order, reference="VQR123456")
    payment.provider_payload = {
        "provider_metadata": {
            "raw_response": {
                "content": "VQR123456",
                "amount": "150000",
                "bankAccount": "0859246671",
                "bankCode": "MB",
            }
        }
    }
    payment.save(update_fields=["provider_payload"])
    mock_test_callback.return_value = {"success": True, "status": "SUCCESS", "message": ""}

    result = VietQRSandboxCallbackService().request_test_callback(transaction_id=payment.id)

    assert result["success"] is True
    assert result["local_payment_updated"] is True
    expected_raw = {
        "content": "VQR123456",
        "amount": "150000",
        "bankAccount": "0859246671",
        "bankCode": "MB",
        "orderId": None,
        "transactionId": None,
        "transactionRefId": None,
        "existing": None,
    }
    mock_test_callback.assert_has_calls([
        call(
            bank_account="0859246671",
            content="VQR123456",
            amount="150000",
            bank_code="MB",
            trans_type="C",
            amount_format="number",
            raw_qr_fields=expected_raw,
        ),
        call(
            bank_account="0859246671",
            content="VQR123456",
            amount="150000",
            bank_code="MB",
            trans_type="C",
            amount_format="string",
            raw_qr_fields=expected_raw,
        ),
    ])


@pytest.mark.django_db
@patch("apps.payments.gateways.vietqr.VietQRGateway.request_test_callback")
def test_request_test_callback_marks_payment_success_and_fulfills_order(mock_test_callback, settings):
    settings.VIETQR_ENV = "dev"
    order = make_order()
    payment = create_vietqr_payment(order=order, amount=Decimal("150000.00"), reference="VQR123456")
    payment.provider_payload = {
        "provider_metadata": {
            "raw_response": {
                "content": "VQR123456",
                "amount": "150000",
                "bankAccount": "0859246671",
                "bankCode": "MB",
            }
        }
    }
    payment.save(update_fields=["provider_payload"])
    mock_test_callback.side_effect = [
        {"success": True, "status": "SUCCESS", "status_code": 200, "variant": "number", "payload": {"content": "VQR123456"}},
        {"success": False, "status": "FAILED", "status_code": 400, "variant": "string"},
    ]

    result = VietQRSandboxCallbackService().request_test_callback(transaction_id=payment.id)

    payment.refresh_from_db()
    order.refresh_from_db()
    assert result["success"] is True
    assert result["local_payment_updated"] is True
    assert payment.status == PaymentStatusChoice.SUCCESS
    assert order.status == OrderStatus.PENDING_PROCESSING
    assert payment.provider_payload["last_test_callback"]["variant"] == "number"


@pytest.mark.django_db
@patch("apps.payments.gateways.vietqr.VietQRGateway.request_test_callback")
def test_request_test_callback_is_idempotent_after_success(mock_test_callback, settings):
    settings.VIETQR_ENV = "dev"
    order = make_order()
    payment = create_vietqr_payment(
        order=order,
        status=PaymentStatusChoice.SUCCESS,
        reference="VQR123456",
    )
    payment.provider_payload = {"provider_metadata": {"raw_response": {"content": "VQR123456"}}}
    payment.save(update_fields=["provider_payload"])

    result = VietQRSandboxCallbackService().request_test_callback(transaction_id=payment.id)

    assert result["success"] is True
    assert result["already_completed"] is True
    assert result["local_payment_updated"] is False
    mock_test_callback.assert_not_called()


@pytest.mark.django_db
@patch("apps.payments.gateways.vietqr.VietQRGateway.request_test_callback")
def test_request_test_callback_provider_failure_leaves_payment_pending(mock_test_callback, settings):
    settings.VIETQR_ENV = "dev"
    order = make_order()
    payment = create_vietqr_payment(order=order)
    payment.provider_payload = {"provider_metadata": {"raw_response": {"content": "VQR123456", "amount": "150000"}}}
    payment.save(update_fields=["provider_payload"])
    mock_test_callback.side_effect = [
        {"success": False, "status": "FAILED", "status_code": 400, "variant": "number"},
        {"success": False, "status": "FAILED", "status_code": 400, "variant": "string"},
    ]

    result = VietQRSandboxCallbackService().request_test_callback(transaction_id=payment.id)

    payment.refresh_from_db()
    order.refresh_from_db()
    assert result["success"] is False
    assert result["local_payment_updated"] is False
    assert payment.status == PaymentStatusChoice.PENDING
    assert order.status == OrderStatus.PENDING_PAYMENT
