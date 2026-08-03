"""
Class: PayPalPaymentView, PayPalCaptureView, PayPalRefundView

Coupling Level:
- Data Coupling with PaymentService because views call service methods with
  typed DTOs (InitiatePaymentRequest, CapturePaymentRequest) containing only
  the primitive fields needed — no raw request objects are passed into the service.
- Data Coupling with serializers because views pass only request.data (a dict)
  and receive validated_data (a dict of primitives) back.
- Data Coupling with payment application services because capture/refund success
  delegates lifecycle changes to PaymentCompletionService/PaymentLifecycleService
  instead of mutating status fields directly in the controller.

Cohesion Level:
- Functional Cohesion because each view class handles exactly one HTTP endpoint:
  PayPalPaymentView → POST /payments/paypal/initiate/
  PayPalCaptureView → POST /payments/paypal/capture/
  PayPalRefundView  → POST /payments/paypal/refund/

Reason:
Views remain transport-oriented: validation, lightweight persistence setup, and
response mapping stay in the controller, while success-state transitions and
order fulfillment go through payment-side lifecycle services.
"""

import logging
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from apps.orders.models import Order

from .completion_service import PaymentCompletionService
from .models import (
    PaymentGatewayChoice,
    PaymentStatusChoice,
    PaymentTransaction,
    RefundMethodChoice,
    RefundStatusChoice,
    RefundTransaction,
)
from .lifecycle_service import PaymentLifecycleService
from .serializers import (
    CapturePayPalPaymentSerializer,
    CreateVietQRPaymentSerializer,
    InitiatePayPalPaymentSerializer,
    PaymentStatusSerializer,
    PaymentTransactionSerializer,
    RefundPaymentSerializer,
    VietQRPaymentSerializer,
    VietQRTestCallbackSerializer,
)
from .services import (
    CapturePaymentRequest,
    InitiatePaymentRequest,
    PaymentService,
)
from .provider_registry import PaymentProviderRegistry
from .vietqr_service import VietQRSandboxCallbackService


def _raise_drf_validation(error: DjangoValidationError) -> None:
    raise ValidationError(error.message_dict if hasattr(error, "message_dict") else error.messages)


def _vietqr_transaction_sync_response(
    *,
    error: bool,
    toast_message: str,
    reftransactionid: str = "",
    error_reason: str | None = None,
) -> dict:
    return {
        "error": error,
        "errorReason": error_reason,
        "toastMessage": toast_message,
        "object": {
            "reftransactionid": reftransactionid,
        },
    }


def _logged_vietqr_sync_response(*, body: dict, http_status: int = status.HTTP_200_OK) -> Response:
    logger.info("VietQR Transaction Sync response=%s", body)
    return Response(body, status=http_status)


def _get_order(order_id: str) -> Order:
    try:
        return Order.objects.get(order_id=order_id)
    except (Order.DoesNotExist, ValueError, DjangoValidationError) as exc:
        raise ValidationError({"order_id": "Order does not exist."}) from exc


def _paypal_amount_from_order(order: Order, currency: str) -> tuple[Decimal, Decimal]:
    source_amount_vnd = Decimal(order.total_amount)
    if hasattr(order, "invoice"):
        source_amount_vnd = Decimal(order.invoice.total_amount_to_pay)

    if source_amount_vnd <= 0:
        raise ValidationError({"order_id": "Order total must be greater than zero."})

    normalized_currency = currency.upper()
    if normalized_currency == "VND":
        return source_amount_vnd.quantize(Decimal("0.01")), source_amount_vnd

    if normalized_currency != "USD":
        raise ValidationError({"currency": "Only USD is supported for PayPal payments."})

    try:
        vnd_per_usd = Decimal(str(settings.PAYPAL_VND_PER_USD))
    except (InvalidOperation, TypeError) as exc:
        raise ValidationError({"currency": "PAYPAL_VND_PER_USD is not configured correctly."}) from exc

    if vnd_per_usd <= 0:
        raise ValidationError({"currency": "PAYPAL_VND_PER_USD must be greater than zero."})

    amount = (source_amount_vnd / vnd_per_usd).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if amount <= 0:
        amount = Decimal("0.01")
    return amount, source_amount_vnd


def _order_amount_vnd(order: Order) -> Decimal:
    if hasattr(order, "invoice"):
        return Decimal(order.invoice.total_amount_to_pay).quantize(Decimal("0.01"))
    return Decimal(order.total_amount).quantize(Decimal("0.01"))


logger = logging.getLogger(__name__)


# /*
#  * SOLID Review
#  * Principle: DIP
#  * Reason: _get_payment_service directly constructs PayPalGateway and RefundService concrete dependencies inside the view module.
#  * Impact: View tests and provider replacement are coupled to concrete PayPal configuration instead of an application-level abstraction.
#  * Improvement: Move payment service construction to a factory/registry or dependency injection boundary outside the controller.
#  */
def _get_payment_service() -> PaymentService:
    """
    Factory helper: builds PaymentService with the PayPal gateway.
    In production, replace with a proper DI container or Django AppConfig.
    """
    from .refund_service import RefundService

    registry = PaymentProviderRegistry()
    initiator = registry.get_payment_initiator(PaymentGatewayChoice.PAYPAL)
    capturer = registry.get_payment_capturer(PaymentGatewayChoice.PAYPAL)
    refund_processor = registry.get_refund_processor(PaymentGatewayChoice.PAYPAL)
    refund_service = RefundService(refund_processor=refund_processor)
    return PaymentService(
        payment_initiator=initiator,
        payment_capturer=capturer,
        refund_service=refund_service,
    )


# /*
#  * SOLID Review
#  * Principle: SRP
#  * Reason: PayPalPaymentView validates HTTP input, computes order amount/currency, delegates gateway initiation, and creates PaymentTransaction records.
#  * Impact: The controller has multiple reasons to change and mixes orchestration/persistence with HTTP response formatting.
#  * Improvement: Move transaction creation and amount selection into a PayPal application service, leaving the view as input/output glue.
#  */
class PayPalPaymentView(APIView):
    """
    POST /payments/paypal/initiate/
    Initiates a PayPal payment, creates a PENDING transaction record,
    and returns the buyer approval URL.

        Coupling Level:
        - Data Coupling with serializers and PaymentService: validates primitives
            and forwards typed DTOs to the service layer.

        Cohesion Level:
        - Functional Cohesion: single responsibility — handle the initiate HTTP
            endpoint and persist the initial transaction record.

        Reason:
        - Views remain thin: validation, persistence of transaction record, and
            delegating business logic to the service layer keeps responsibilities
            separated and testable.
    """

    def post(self, request):
        serializer = InitiatePayPalPaymentSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        order = _get_order(data["order_id"])
        currency = data["currency"].upper()
        paypal_amount = data.get("amount")
        source_amount_vnd = _order_amount_vnd(order)
        if paypal_amount is None:
            paypal_amount, source_amount_vnd = _paypal_amount_from_order(order, currency)
        service = _get_payment_service()

        response = service.initiate_payment(
            InitiatePaymentRequest(
                order_id=data["order_id"],
                amount=float(paypal_amount),
                currency=currency,
                return_url=data["return_url"],
                cancel_url=data["cancel_url"],
                description=data.get("description", ""),
            )
        )

        if not response.success:
            return Response(
                {"error": response.error_message},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        # Create the transaction record immediately so capture can find it
        transaction = PaymentTransaction.objects.create(
            order=order,
            gateway=PaymentGatewayChoice.PAYPAL,
            provider_order_id=response.provider_order_id,
            amount=source_amount_vnd,
            currency="VND",
            status=PaymentStatusChoice.PENDING,
            provider_payload={
                "paypal_amount": f"{paypal_amount:.2f}",
                "paypal_currency": currency,
                "source_amount_vnd": f"{source_amount_vnd:.2f}",
            },
        )

        return Response(
            {
                "provider_order_id": response.provider_order_id,
                "approval_url": response.approval_url,
                "transaction_id": transaction.id,
                "amount": f"{paypal_amount:.2f}",
                "currency": currency,
                "source_amount_vnd": f"{source_amount_vnd:.2f}",
            },
            status=status.HTTP_201_CREATED,
        )


# /*
#  * SOLID Review
#  * Principle: SRP
#  * Reason: PayPalCaptureView captures the PayPal order, prepares provider metadata, and returns the HTTP response.
#  * Impact: If the view mutates payment success state or fulfills orders directly, lifecycle policy leaks back into the controller.
#  * Improvement: Delegate successful payment completion to PaymentCompletionService so the controller only validates input and maps the response.
#  */
class PayPalCaptureView(APIView):
    """
    POST /payments/paypal/capture/
    Captures an approved PayPal payment and marks the transaction as COMPLETED.
    """

    def post(self, request):
        serializer = CapturePayPalPaymentSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        service = _get_payment_service()
        completion_service = PaymentCompletionService()

        response = service.capture_payment(
            CapturePaymentRequest(
                provider_order_id=data["provider_order_id"],
                internal_order_id=data["internal_order_id"],
            )
        )

        if not response.success:
            PaymentTransaction.objects.filter(
                order_id=data["internal_order_id"],
                gateway=PaymentGatewayChoice.PAYPAL,
                status=PaymentStatusChoice.PENDING,
            ).first()
            return Response(
                {"error": response.error_message},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        transaction = PaymentTransaction.objects.filter(
            order_id=data["internal_order_id"],
            gateway=PaymentGatewayChoice.PAYPAL,
        ).first()

        if transaction:
            payload = dict(transaction.provider_payload or {})
            payload["paypal_captured_amount"] = (
                f"{Decimal(str(response.captured_amount or 0)).quantize(Decimal('0.01')):.2f}"
            )
            payload.setdefault("paypal_currency", "USD")
            transaction = completion_service.complete_successful_payment(
                transaction,
                capture_id=response.transaction_id or "",
                provider_payload_patch=payload,
            )
        else:
            order = _get_order(data["internal_order_id"])
            amount_vnd = _order_amount_vnd(order)
            transaction = PaymentTransaction.objects.create(
                order=order,
                gateway=PaymentGatewayChoice.PAYPAL,
                provider_order_id=data["provider_order_id"],
                amount=amount_vnd,
                currency="VND",
                status=PaymentStatusChoice.PENDING,
                provider_payload={
                    "paypal_captured_amount": (
                        f"{Decimal(str(response.captured_amount or 0)).quantize(Decimal('0.01')):.2f}"
                    ),
                    "paypal_currency": "USD",
                    "source_amount_vnd": f"{amount_vnd:.2f}",
                },
            )
            transaction = completion_service.complete_successful_payment(
                transaction,
                capture_id=response.transaction_id or "",
            )

        return Response(
            PaymentTransactionSerializer(transaction).data,
            status=status.HTTP_200_OK,
        )


# /*
#  * SOLID Review
#  * Principle: SRP/DIP
#  * Reason: PayPalRefundView validates HTTP input, derives the internal refund amount from Order/Invoice, calls the refund service, and persists refund transaction records.
#  * Impact: Refund policy changes and persistence changes require controller edits, while the view still depends on the concrete payment-service factory.
#  * Improvement: Introduce a refund use-case service that receives validated DTOs and encapsulates refund amount selection, gateway invocation, and refund record creation.
#  */
class PayPalRefundView(APIView):
    """
    POST /payments/paypal/refund/
    Issues a full refund for a cancelled order and marks the transaction as REFUNDED.
    """

    def post(self, request):
        serializer = RefundPaymentSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        service = _get_payment_service()
        order = _get_order(data["order_id"])
        internal_refund_amount = getattr(order, "invoice", None)
        internal_refund_amount = (
            internal_refund_amount.total_amount_to_pay
            if internal_refund_amount is not None
            else order.total_amount
        )

        response = service.refund_payment(
            order_id=data["order_id"],
            capture_id=data["capture_id"],
            amount=float(data["amount"]),
            currency=data["currency"],
            reason=data.get("reason", "Customer cancelled order"),
        )

        if not response.success:
            return Response(
                {"error": response.error_message},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        transaction = PaymentTransaction.objects.filter(
            order_id=data["order_id"],
            gateway=PaymentGatewayChoice.PAYPAL,
            status=PaymentStatusChoice.SUCCESS,
        ).first()

        if transaction:
            PaymentLifecycleService().mark_refunded(
                transaction,
                refund_id=response.refund_id,
            )
            RefundTransaction.objects.create(
                payment_transaction=transaction,
                refund_amount=internal_refund_amount,
                refund_reason=data.get("reason", "Customer cancelled order"),
                refund_status=RefundStatusChoice.SUCCESS,
                refund_method=RefundMethodChoice.PAYPAL_API,
            )

        return Response(
            {
                "refund_id": response.refund_id,
                "refunded_amount": response.refunded_amount,
                "transaction": PaymentTransactionSerializer(transaction).data if transaction else None,
            },
            status=status.HTTP_200_OK,
        )


class VietQRQRCodeView(APIView):
    """
    POST /payments/vietqr/qr-code/
    Creates a PENDING VietQR transaction and returns the mock QR payload.
    """

    def post(self, request):
        serializer = CreateVietQRPaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            initiator = PaymentProviderRegistry().get_payment_initiator(
                PaymentGatewayChoice.VIETQR,
            )
            result = initiator.create_payment(
                order_id=serializer.validated_data["order_id"],
                amount=float(serializer.validated_data["amount"]),
                currency="VND",
                return_url="",
                cancel_url="",
            )
            payment = PaymentTransaction.objects.get(id=result.transaction_id)
        except DjangoValidationError as error:
            _raise_drf_validation(error)
        return Response(VietQRPaymentSerializer(payment).data, status=status.HTTP_201_CREATED)


class VietQRTestCallbackView(APIView):
    """
    POST /payments/vietqr/test-callback/
    Requests VietQR sandbox to simulate a payment callback for a generated QR.
    """

    def post(self, request):
        serializer = VietQRTestCallbackSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            result = VietQRSandboxCallbackService().request_test_callback(
                transaction_id=serializer.validated_data["transaction_id"],
            )
        except DjangoValidationError as error:
            _raise_drf_validation(error)
        except Exception as exc:
            logger.exception("VietQR sandbox test callback endpoint error: %s", exc)
            return Response(
                {
                    "success": False,
                    "status": "FAILED",
                    "sandbox_only": True,
                    "error": "Unable to request VietQR sandbox test callback.",
                    "details": str(exc),
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

        if isinstance(result, dict):
            result.setdefault("status", "SUCCESS" if result.get("success") else "FAILED")
            result.setdefault("message", "" if result.get("success") else "VietQR sandbox test callback failed.")

        return Response(result, status=status.HTTP_200_OK)


class VietQRStatusView(APIView):
    """
    GET /payments/<transaction_id>/status/
    Returns the current status snapshot of a payment transaction.
    """

    def get(self, request, transaction_id):
        try:
            payment = PaymentTransaction.objects.get(id=transaction_id)
        except PaymentTransaction.DoesNotExist as exc:
            raise NotFound("Payment transaction not found.") from exc
        return Response(PaymentStatusSerializer(payment).data)


class VietQRCallbackTokenView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    """
    Endpoint for VietQR to authenticate and get Bearer token for callbacks.

    POST /api/payments/vietqr/token-generate/
    """

    def post(self, request):
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        if not auth_header.startswith("Basic "):
            return Response(
                {"error": "Missing or invalid Authorization header"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        import base64

        try:
            auth_encoded = auth_header[6:]
            credentials = base64.b64decode(auth_encoded).decode("utf-8")
            username, password = credentials.split(":", 1)
        except Exception as e:
            logger.warning(f"Invalid Basic Auth format: {e}")
            return Response(
                {"error": "Invalid Authorization header"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        from django.conf import settings

        expected_username = settings.VIETQR_CALLBACK_USERNAME
        expected_password = settings.VIETQR_CALLBACK_PASSWORD

        if username != expected_username or password != expected_password:
            logger.warning("VietQR callback auth failed: invalid credentials")
            return Response(
                {"error": "Invalid credentials"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        token = self._generate_callback_token()

        return Response(
            {
                "access_token": token,
                "token_type": "Bearer",
                "expires_in": getattr(settings, "VIETQR_CALLBACK_TOKEN_TTL_SECONDS", 300),
            },
            status=status.HTTP_200_OK,
        )

    def _generate_callback_token(self) -> str:
        import jwt
        import time

        from django.conf import settings

        ttl = getattr(settings, "VIETQR_CALLBACK_TOKEN_TTL_SECONDS", 300)

        payload = {
            "iat": int(time.time()),
            "exp": int(time.time()) + ttl,
            "type": "vietqr_callback",
        }

        return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


# /*
#  * SOLID Review
#  * Principle: SRP/DIP
#  * Reason: VietQRTransactionSyncView verifies callback bearer tokens, parses provider payloads, calls VietQRService, and formats VietQR-specific response envelopes.
#  * Impact: Authentication, provider mapping, and payment confirmation are coupled in one controller, reducing testability and making callback changes risky.
#  * Improvement: Extract token verification and payload mapping into callback handler services injected into the view.
#  */
class VietQRTransactionSyncView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    """
    Minimal sandbox callback receiver kept only for VietQR connectivity checks.

    POST /api/payments/vietqr/bank/api/transaction-sync
    """

    def post(self, request):
        # Log incoming callback for traceability
        logger.info("=" * 80)
        logger.info("VietQR Transaction Sync received")
        logger.info("VietQR Transaction Sync callback received")
        logger.info("path=%s method=%s", request.path, request.method)
        headers = dict(request.headers)
        if "Authorization" in headers:
            headers["Authorization"] = "***redacted***"
        logger.info("headers=%s", headers)
        try:
            raw_body = request.body.decode("utf-8", errors="replace")
            logger.info("raw_body=%s", raw_body)
        except Exception as e:
            logger.warning("Could not decode request body: %s", e)
        logger.info("data=%s", getattr(request, "data", None))
        logger.info("=" * 80)

        # Verify Bearer token if present; sandbox integration may omit it.
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        token_verified = False
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            if not self._verify_callback_token(token):
                logger.warning("VietQR callback: Invalid or expired Bearer token")
                return _logged_vietqr_sync_response(
                    body=_vietqr_transaction_sync_response(
                        error=True,
                        error_reason="Invalid Bearer token",
                        toast_message="Invalid Bearer token",
                    ),
                )
            token_verified = True
            logger.info("VietQR callback: Bearer token verified")
        else:
            logger.info("VietQR callback: No Bearer token provided (test callback or dev)")

        payload = request.data if isinstance(request.data, dict) else {}
        reference = (
            payload.get("transactionId")
            or payload.get("transactionid")
            or payload.get("referenceNumber")
            or payload.get("referencenumber")
            or ""
        )

        # A provider callback with the complete signed payload settles the
        # matching VietQR transaction. Short sandbox connectivity probes are
        # acknowledged but intentionally do not mutate payment/order state.
        complete_callback_fields = ("orderId", "content", "bankAccount", "amount", "successFlag")
        if token_verified and all(field in payload for field in complete_callback_fields):
            try:
                payment = PaymentTransaction.objects.select_related("order").get(
                    gateway=PaymentGatewayChoice.VIETQR,
                    transaction_reference=str(payload["content"]),
                )
                callback_amount = Decimal(str(payload["amount"]))
            except (PaymentTransaction.DoesNotExist, InvalidOperation, TypeError, ValueError):
                return _logged_vietqr_sync_response(
                    body=_vietqr_transaction_sync_response(
                        error=True,
                        error_reason="Payment transaction does not match callback",
                        toast_message="Payment transaction does not match callback",
                        reftransactionid=str(reference),
                    ),
                )

            if payload.get("successFlag") is not True or callback_amount != payment.amount:
                return _logged_vietqr_sync_response(
                    body=_vietqr_transaction_sync_response(
                        error=True,
                        error_reason="Callback status or amount is invalid",
                        toast_message="Callback status or amount is invalid",
                        reftransactionid=str(reference),
                    ),
                )

            PaymentCompletionService().complete_successful_payment(
                payment,
                capture_id=str(reference),
                provider_payload_patch={"vietqr_callback": payload},
                note="Completed by verified VietQR callback",
            )
            return _logged_vietqr_sync_response(
                body=_vietqr_transaction_sync_response(
                    error=False,
                    toast_message="Transaction processed successfully",
                    reftransactionid=str(reference),
                ),
            )

        if not reference:
            return _logged_vietqr_sync_response(
                body=_vietqr_transaction_sync_response(
                    error=True,
                    error_reason="Missing transaction reference",
                    toast_message="Missing transaction reference",
                ),
            )

        logger.info("Acknowledging VietQR sandbox callback without payment mutation")
        return _logged_vietqr_sync_response(
            body=_vietqr_transaction_sync_response(
                error=False,
                toast_message="Callback received successfully",
                reftransactionid=str(reference),
            ),
        )

    def _verify_callback_token(self, token: str) -> bool:
        import jwt
        import time

        from django.conf import settings

        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
            if payload.get("type") != "vietqr_callback":
                return False
            if int(time.time()) > payload.get("exp", 0):
                return False
            return True
        except jwt.InvalidTokenError:
            logger.warning("Invalid VietQR callback token")
            return False
