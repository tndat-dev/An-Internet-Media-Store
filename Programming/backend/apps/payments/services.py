"""
Class: PaymentService

Coupling Level:
- Data Coupling with PaymentGateway (interface) because it passes only
  primitive/DTO values when calling gateway methods (order_id, amount,
  currency, return_url). No large model objects cross the boundary.
- Data Coupling with RefundService because it passes a RefundRequest DTO
  containing only the fields needed for the refund operation.
- Stamp Coupling (acceptable) with Order model when loading an order before
  payment — the full Order object is used because multiple fields
  (total_amount, currency, status) are genuinely needed. This is an
  intentional trade-off to avoid excessive parameter lists.

Cohesion Level:
- Functional Cohesion because this class orchestrates the payment lifecycle
  for an AIMS order: initiate → capture → record transaction.
  All methods belong to this single responsibility.
  Gateway-specific logic (PayPal API calls, VietQR QR generation) is
  delegated to the injected PaymentGateway, keeping this class focused.

Reason:
PaymentService does NOT contain if/else branches selecting between PayPal
and VietQR — that was the old control-coupled design. Instead, the correct
gateway is injected at construction time (via a Factory or DI container),
so PaymentService only calls the abstract PaymentGateway interface.
This eliminates control coupling and makes PaymentService open for extension
(new gateways) without modification.
"""

import logging
from dataclasses import dataclass
from typing import Optional

from .gateways.base import PaymentCapturer, PaymentInitiator
from .refund_service import RefundRequest, RefundResponse, RefundService

logger = logging.getLogger(__name__)


@dataclass
class InitiatePaymentRequest:
    """DTO for starting a payment flow."""
    order_id: str
    amount: float
    currency: str
    return_url: str
    cancel_url: str
    description: str = ""


@dataclass
class InitiatePaymentResponse:
    success: bool
    provider_order_id: Optional[str] = None
    approval_url: Optional[str] = None   # PayPal redirect URL
    qr_data: Optional[str] = None        # VietQR QR string
    error_message: Optional[str] = None


@dataclass
class CapturePaymentRequest:
    """DTO for capturing a payment after buyer approval."""
    provider_order_id: str  
    internal_order_id: str 

@dataclass
class CapturePaymentResponse:
    success: bool
    transaction_id: Optional[str] = None
    captured_amount: Optional[float] = None
    error_message: Optional[str] = None


# /*
#  * SOLID Review
#  * Principle: SRP/ISP
#  * Reason: PaymentService exposes initiation, capture, and refund orchestration through one service even though refund processing has different rules and provider capability requirements.
#  * Impact: Callers that only need payment capture still depend on refund-oriented behavior, and the service can grow as more payment operations are added.
#  * Improvement: Keep payment orchestration separate from refund orchestration and depend on narrower provider capability interfaces.
#  */
class PaymentService:
    """
    Orchestrates the payment lifecycle: initiate → capture → refund.
    Depends on PaymentGateway abstraction, not on any concrete provider.

        Coupling Level:
        - Data Coupling with PaymentGateway: passes primitive values and DTOs only.
        - Low Control Coupling: the concrete gateway is injected; PaymentService
            doesn't use if/else to select providers.

        Cohesion Level:
        - Functional Cohesion: single responsibility — orchestrate payment flows.

        Reason:
        - Keeps orchestration logic separate from transport and provider details.
            Gateway-specific logic is delegated to implementations behind the
            PaymentGateway interface.
    """

    def __init__(
        self,
        payment_initiator: PaymentInitiator,
        payment_capturer: PaymentCapturer,
        refund_service: RefundService,
    ):
        self._payment_initiator = payment_initiator
        self._payment_capturer = payment_capturer
        self._refund_service = refund_service

    def initiate_payment(self, request: InitiatePaymentRequest) -> InitiatePaymentResponse:
        """
        Start a payment flow. Returns approval_url (PayPal) or qr_data (VietQR).
        """
        logger.info("Initiating payment for order %s, amount %.2f %s",
                    request.order_id, request.amount, request.currency)

        result = self._payment_initiator.create_payment(
            order_id=request.order_id,
            amount=request.amount,
            currency=request.currency,
            return_url=request.return_url,
            cancel_url=request.cancel_url,
            description=request.description,
        )

        if not result.success:
            logger.error("Payment initiation failed for order %s: %s",
                         request.order_id, result.error_message)
            return InitiatePaymentResponse(
                success=False,
                error_message=result.error_message,
            )

        return InitiatePaymentResponse(
            success=True,
            provider_order_id=result.transaction_id,
            approval_url=result.approval_url,
            qr_data=result.raw_response.get("qr_data") if result.raw_response else None,
        )

    def capture_payment(self, request: CapturePaymentRequest) -> CapturePaymentResponse:
        """
        Capture a payment after buyer approval/scan.
        """
        logger.info("Capturing payment for provider order %s (internal: %s)",
                    request.provider_order_id, request.internal_order_id)

        result = self._payment_capturer.capture_payment(
            provider_order_id=request.provider_order_id,
        )

        if not result.success:
            logger.error("Capture failed for order %s: %s",
                         request.internal_order_id, result.error_message)
            return CapturePaymentResponse(
                success=False,
                error_message=result.error_message,
            )

        return CapturePaymentResponse(
            success=True,
            transaction_id=result.transaction_id,
            captured_amount=result.captured_amount,
        )

    def refund_payment(
        self,
        order_id: str,
        capture_id: str,
        amount: float,
        currency: str,
        reason: str = "Customer cancelled order",
    ) -> RefundResponse:
        """
        Delegate refund to RefundService with a typed DTO.
        """
        return self._refund_service.refund_order(
            RefundRequest(
                order_id=order_id,
                capture_id=capture_id,
                amount=amount,
                currency=currency,
                reason=reason,
            )
        )
