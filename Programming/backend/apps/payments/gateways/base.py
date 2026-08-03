"""
Class: PaymentGateway (Abstract Base Class)

Coupling Level:
- Data Coupling with PaymentService because it receives only the minimal
  necessary data (amount, currency, order_id, return_url) via method parameters.
- Data Coupling with RefundService because refund methods accept only the
  transaction_id and amount needed to process the refund.

Cohesion Level:
- Functional Cohesion because this abstract class defines a single, clear
  contract: the interface for all payment gateway implementations.
  Every method here belongs to the payment gateway responsibility.

Reason:
Introducing this abstract base class decouples PaymentService from any
concrete payment provider (PayPal, VietQR, Stripe, etc.).
PaymentService depends only on PaymentGateway, not on provider-specific SDKs.
New gateways can be added without modifying existing service logic.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class PaymentResult:
    """DTO representing the result of a payment operation.

    Coupling Level:
    - Data Coupling: simple DTO carrying primitive and small structured values
      between gateway implementations and service layer.

    Cohesion Level:
    - Functional Cohesion: this class has a single responsibility: carry
      payment result data.

    Reason:
    - Using small DTOs keeps boundaries explicit and reduces coupling between
      layers; these objects are intentionally lightweight.
    """
    success: bool
    transaction_id: Optional[str] = None
    approval_url: Optional[str] = None
    raw_response: Optional[dict] = None
    error_message: Optional[str] = None


@dataclass
class RefundResult:
    """DTO representing the result of a refund operation.

    Coupling Level:
    - Data Coupling: used to return refund results from gateway to RefundService.

    Cohesion Level:
    - Functional Cohesion: single-purpose DTO for refund results.

    Reason:
    - Keeps refund response data structured and independent from transport.
    """
    success: bool
    refund_id: Optional[str] = None
    refunded_amount: Optional[float] = None
    raw_response: Optional[dict] = None
    error_message: Optional[str] = None


@dataclass
class QRCodeResult:
    """DTO representing a generated QR code for a VietQR payment.

    Coupling Level:
    - Data Coupling: carries only the QR payload/reference produced by the
      VietQR gateway back to the VietQR service.

    Cohesion Level:
    - Functional Cohesion: single-purpose DTO for QR generation results.

    Reason:
    - Keeps the QR gateway output structured and free of transport details so
      the service layer can persist it without knowing provider specifics.
    """
    transaction_reference: str
    qr_payload: str
    qr_image_url: str
    provider_metadata: Optional[dict] = None


@dataclass
class CaptureResult:
    """DTO representing the result of a payment capture.

    Coupling Level:
    - Data Coupling: small DTO exchanged between gateway and service layers.

    Cohesion Level:
    - Functional Cohesion: holds capture outcome details only.

    Reason:
    - Simplifies communication of capture outcomes without leaking transport
      details into business logic.
    """
    success: bool
    transaction_id: Optional[str] = None
    captured_amount: Optional[float] = None
    raw_response: Optional[dict] = None
    error_message: Optional[str] = None


class UnsupportedPaymentCapability(Exception):
    """Raised when a provider does not implement the requested capability."""


class PaymentInitiator(ABC):
    """Capability interface for starting a payment flow."""

    @abstractmethod
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
        Initiate a payment and return approval URL or QR data.
        """
        pass


class PaymentCapturer(ABC):
    """Capability interface for confirming a previously initiated payment."""

    @abstractmethod
    def capture_payment(self, provider_order_id: str) -> CaptureResult:
        """
        Capture/confirm a previously created payment.
        """
        pass


class RefundProcessor(ABC):
    """Capability interface for providers that support automatic refunds."""

    @abstractmethod
    def refund_payment(
        self,
        capture_id: str,
        amount: float,
        currency: str,
        reason: str = "",
    ) -> RefundResult:
        """
        Refund a captured payment fully or partially.
        """
        pass


class PaymentGateway(PaymentInitiator, PaymentCapturer, ABC):
    """
    Backward-compatible composite capability for providers that both initiate
    and capture payments. Refund support is split into RefundProcessor.
    """
