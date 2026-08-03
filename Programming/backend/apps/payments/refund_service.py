"""
Class: RefundService

Coupling Level:
- Data Coupling with PaymentGateway because it calls gateway.refund_payment()
  with only the primitive values needed: capture_id (str), amount (float),
  currency (str), reason (str).
- Data Coupling with PaymentTransactionRepository because it passes only the
  transaction_id to look up a transaction, and receives back a small DTO.
- Stamp Coupling (minor, acceptable) with PaymentTransaction model when
  updating the refund status — the full model object is loaded, but this is
  standard ORM practice within Django and is an intentional design choice,
  not a lazy shortcut.

Cohesion Level:
- Functional Cohesion because this class has one clear responsibility:
  processing refunds. Every method (refund_order, _validate_refundable,
  _record_refund) contributes directly to that single purpose.

Reason:
Refund logic is separated from PaymentService to avoid PaymentService
growing into a low-cohesion "god service". RefundService owns the refund
business rules (e.g., only pending/approved orders can be refunded, refund
amount must not exceed original capture amount) and delegates the actual
API call to the injected PaymentGateway.
"""

import logging
from dataclasses import dataclass
from typing import Optional

from .gateways.base import RefundProcessor, RefundResult

logger = logging.getLogger(__name__)


@dataclass
class RefundRequest:
    """DTO carrying only the data RefundService needs."""
    order_id: str
    capture_id: str
    amount: float
    currency: str
    reason: str = "Customer requested cancellation"


@dataclass
class RefundResponse:
    success: bool
    refund_id: Optional[str] = None
    refunded_amount: Optional[float] = None
    error_message: Optional[str] = None


# /*
#  * SOLID Review
#  * Principle: ISP/DIP
#  * Reason: RefundService depends on the broad PaymentGateway abstraction even though it only needs refund_payment capability.
#  * Impact: Refund-only logic is coupled to create/capture methods, making manual-refund or non-card providers harder to substitute cleanly.
#  * Improvement: Depend on a narrower RefundProcessor interface and register only providers that support automatic refunds.
#  */
class RefundService:
    """
    Handles the refund business logic for cancelled AIMS orders.
    Currently supports PayPal refunds only (VietQR refunds are manual).

        Coupling Level:
        - Data Coupling with PaymentGateway (uses refund_payment) and with ORM
            model PaymentTransaction for recording refund status.

        Cohesion Level:
        - Functional Cohesion: single responsibility — validate and process refunds.

        Reason:
        - Isolating refund rules here prevents PaymentService becoming a low-cohesion
            god-class and centralizes refund-related policies for easier testing.
    """

    def __init__(self, refund_processor: RefundProcessor):
        # Depends on abstraction, not on a concrete gateway class
        self._gateway = refund_processor

    def refund_order(self, request: RefundRequest) -> RefundResponse:
        """
        Process a full refund for a cancelled order.

        Business rules enforced here:
        - Only orders with a valid capture_id can be refunded automatically.
        - Refund amount must equal the original captured amount (full refund only).
        """
        if not request.capture_id:
            return RefundResponse(
                success=False,
                error_message="No capture ID found. Manual refund required.",
            )

        if request.amount <= 0:
            return RefundResponse(
                success=False,
                error_message="Refund amount must be greater than zero.",
            )

        logger.info(
            "Initiating refund for order %s, capture %s, amount %.2f %s",
            request.order_id,
            request.capture_id,
            request.amount,
            request.currency,
        )

        result: RefundResult = self._gateway.refund_payment(
            capture_id=request.capture_id,
            amount=request.amount,
            currency=request.currency,
            reason=request.reason,
        )

        if result.success:
            logger.info(
                "Refund successful for order %s — refund_id: %s",
                request.order_id,
                result.refund_id,
            )
            return RefundResponse(
                success=True,
                refund_id=result.refund_id,
                refunded_amount=result.refunded_amount,
            )

        logger.error(
            "Refund failed for order %s: %s",
            request.order_id,
            result.error_message,
        )
        return RefundResponse(
            success=False,
            error_message=result.error_message,
        )
