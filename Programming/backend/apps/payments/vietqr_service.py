import logging
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError

from apps.orders.models import Order
from apps.payments.completion_service import PaymentCompletionService
from apps.payments.gateways.base import PaymentResult
from apps.payments.gateways.vietqr import VietQRGateway
from apps.payments.lifecycle_service import PaymentLifecycleService
from apps.payments.models import (
    PaymentGatewayChoice,
    PaymentStatusChoice,
    PaymentTransaction,
)

logger = logging.getLogger(__name__)


# /*
#  * SOLID Review
#  * Principle: SRP/DIP
#  * Reason: VietQRService creates transactions, calls the concrete VietQRGateway, changes payment state from sandbox test-callback results, and triggers order fulfillment.
#  * Impact: QR business workflow is tightly coupled to persistence, gateway construction, and order integration, making tests and provider replacement harder.
#  * Improvement: Inject gateway/order fulfillment collaborators and separate transaction persistence from callback validation policy.
#  */
class VietQRService:
    """
    VietQR payment initiation business rules live here: create a QR transaction
    and persist the provider QR metadata.

    Coupling Level:
    - Data Coupling with VietQRGateway: receives a QRCodeResult DTO only.
    - Stamp Coupling (acceptable): persists/loads the PaymentTransaction ORM
      object to drive its lifecycle helpers (mark_completed/mark_failed).

    Cohesion Level:
    - Functional Cohesion: every method serves VietQR payment initiation.
    """

    def __init__(
        self,
        gateway: VietQRGateway | None = None,
        lifecycle_service: PaymentLifecycleService | None = None,
    ) -> None:
        self.gateway = gateway or VietQRGateway()
        self._lifecycle_service = lifecycle_service or PaymentLifecycleService()

    def create_payment(
        self,
        order_id: str,
        amount: float,
        currency: str,
        return_url: str,
        cancel_url: str,
        description: str = "",
    ) -> PaymentResult:
        """
        Adapter entrypoint so VietQR can be selected through the same provider
        registry boundary as other payment initiators.
        """
        if str(currency).upper() != "VND":
            return PaymentResult(
                success=False,
                error_message="VietQR payments only support VND.",
            )

        payment = self.create_qr_payment(
            order_id=order_id,
            amount=Decimal(str(amount)),
        )
        payload = payment.provider_payload or {}
        return PaymentResult(
            success=True,
            transaction_id=str(payment.id),
            raw_response={
                "transaction_reference": payment.transaction_reference,
                "qr_payload": payload.get("qr_payload", ""),
                "qr_image_url": payload.get("qr_image_url", ""),
                "qr_code": payload.get("qr_code", ""),
                "qr_link": payload.get("qr_link", ""),
            },
        )

    def create_qr_payment(self, *, order_id: str, amount: Decimal) -> PaymentTransaction:
        """
        Create VietQR payment transaction and generate QR.

        Flow:
        1. Create PENDING payment record first
        2. Use payment.id to generate short order_id
        3. Call gateway to generate real QR
        4. If gateway fails, mark as FAILED
        5. Return transaction with QR data
        """
        if not order_id or not order_id.strip():
            raise ValidationError({"order_id": "Order id is required."})
        if Decimal(amount) <= 0:
            raise ValidationError({"amount": "Amount must be greater than zero."})

        try:
            order = Order.objects.get(order_id=order_id.strip())
        except (Order.DoesNotExist, ValueError) as exc:
            raise ValidationError({"order_id": "Order does not exist."}) from exc

        # Create payment transaction first
        payment = PaymentTransaction.objects.create(
            order=order,
            gateway=PaymentGatewayChoice.VIETQR,
            status=PaymentStatusChoice.PENDING,
            amount=Decimal(amount),
            currency="VND",
        )

        try:
            # Generate short order ID using payment.id
            qr_result = self.gateway.create_qr_code(
                order_id=order_id.strip(),
                amount=Decimal(amount),
                payment_id=payment.id,
            )

            # Update payment with QR data
            payment.transaction_reference = qr_result.transaction_reference
            payment.provider_payload = {
                "provider": self.gateway.provider_name,
                "qr_payload": qr_result.qr_payload,
                "qr_image_url": qr_result.qr_image_url,
                "qr_code": qr_result.provider_metadata.get("qr_code", ""),
                "qr_link": qr_result.provider_metadata.get("qr_link", ""),
                "provider_metadata": qr_result.provider_metadata or {},
            }
            payment.transaction_content = qr_result.transaction_reference
            payment.save(update_fields=[
                "transaction_reference",
                "transaction_content",
                "provider_payload",
                "updated_at",
            ])

            raw_response = (payment.provider_payload.get("provider_metadata") or {}).get("raw_response", {})
            raw_dump = {
                "content": raw_response.get("content"),
                "amount": raw_response.get("amount"),
                "bankAccount": raw_response.get("bankAccount"),
                "bankCode": raw_response.get("bankCode"),
                "orderId": raw_response.get("orderId"),
                "transactionId": raw_response.get("transactionId"),
                "transactionRefId": raw_response.get("transactionRefId"),
                "existing": raw_response.get("existing"),
            }
            logger.info("VietQR raw QR response saved payment_id=%s raw=%s", payment.id, raw_dump)
            logger.info(f"VietQR payment {payment.id} created with ref {qr_result.transaction_reference}")
            return payment

        except Exception as e:
            self._lifecycle_service.mark_failed(
                payment,
                reason=str(e),
                provider_payload_patch={"error": str(e)},
            )

            logger.error(f"VietQR payment {payment.id} failed: {e}")
            raise


def _vietqr_raw_qr_fields(payment: PaymentTransaction) -> tuple[dict, dict]:
    metadata = (payment.provider_payload or {}).get("provider_metadata", {})
    raw_response = metadata.get("raw_response", {})
    raw_qr_fields = {
        "content": raw_response.get("content"),
        "amount": raw_response.get("amount"),
        "bankAccount": raw_response.get("bankAccount"),
        "bankCode": raw_response.get("bankCode"),
        "orderId": raw_response.get("orderId"),
        "transactionId": raw_response.get("transactionId"),
        "transactionRefId": raw_response.get("transactionRefId"),
        "existing": raw_response.get("existing"),
    }
    return metadata, raw_qr_fields


class VietQRSandboxCallbackService:
    """Dev-only sandbox callback flow for local VietQR payment completion."""

    def __init__(
        self,
        gateway: VietQRGateway | None = None,
        completion_service: PaymentCompletionService | None = None,
    ) -> None:
        self.gateway = gateway or VietQRGateway()
        self._completion_service = completion_service or PaymentCompletionService()

    def request_test_callback(self, *, transaction_id: int) -> dict:
        if getattr(settings, "VIETQR_ENV", "dev") != "dev":
            raise ValidationError({"environment": "VietQR test callback is only available in dev."})

        try:
            payment = PaymentTransaction.objects.get(
                id=transaction_id,
                gateway=PaymentGatewayChoice.VIETQR,
            )
        except PaymentTransaction.DoesNotExist as exc:
            raise ValidationError({"transaction_id": "VietQR payment transaction does not exist."}) from exc

        metadata, raw_qr_fields = _vietqr_raw_qr_fields(payment)
        raw_response = metadata.get("raw_response", {})
        logger.info("VietQR test callback raw QR fields payment_id=%s raw=%s", payment.id, raw_qr_fields)

        if payment.status == PaymentStatusChoice.SUCCESS:
            return {
                "success": True,
                "sandbox_only": True,
                "already_completed": True,
                "local_payment_updated": False,
                "attempts": [],
                "raw_qr_fields": raw_qr_fields,
                "status": "SUCCESS",
                "message": "Payment already marked successful.",
            }

        if payment.status != PaymentStatusChoice.PENDING:
            raise ValidationError({"status": "Only pending VietQR payments can request a test callback."})

        content = raw_response.get("content") if raw_response else None
        if content is None:
            content = payment.transaction_reference or metadata.get("content") or ""
        bank_account = raw_response.get("bankAccount") or metadata.get("bank_account") or settings.VIETQR_BANK_ACCOUNT
        bank_code = raw_response.get("bankCode") or metadata.get("bank_code") or settings.VIETQR_BANK_CODE
        amount = raw_response.get("amount") or metadata.get("amount") or payment.amount

        if not content:
            raise ValidationError({"content": "VietQR callback content is missing."})

        attempts = []
        for amount_format in ("number", "string"):
            attempts.append(self.gateway.request_test_callback(
                bank_account=bank_account,
                content=content,
                amount=amount,
                bank_code=bank_code,
                trans_type="C",
                amount_format=amount_format,
                raw_qr_fields=raw_qr_fields,
            ))

        provider_success = any(attempt.get("success") for attempt in attempts)
        result = {
            "success": provider_success,
            "sandbox_only": True,
            "attempts": attempts,
            "raw_qr_fields": raw_qr_fields,
        }
        if not provider_success:
            result["local_payment_updated"] = False
            return result

        provider_result = next(attempt for attempt in attempts if attempt.get("success"))
        self._completion_service.complete_successful_payment(
            payment,
            capture_id=provider_result.get("transaction_id") or payment.capture_id or "",
            provider_payload_patch={
                "last_test_callback": {
                    "status": provider_result.get("status", "SUCCESS"),
                    "status_code": provider_result.get("status_code"),
                    "variant": provider_result.get("variant"),
                    "payload": provider_result.get("payload", {}),
                    "details": provider_result.get("details"),
                    "raw_qr_fields": raw_qr_fields,
                }
            },
        )

        result["local_payment_updated"] = True
        return result
