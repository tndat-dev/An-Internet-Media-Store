from django.conf import settings

from .gateways.base import (
    PaymentCapturer,
    PaymentInitiator,
    RefundProcessor,
    UnsupportedPaymentCapability,
)
from .gateways.paypal import PayPalGateway
from .models import PaymentGatewayChoice
from .vietqr_service import VietQRService


class PaymentProviderRegistry:
    """Central provider selection boundary for payment capabilities."""

    def get_payment_initiator(self, gateway_name: str) -> PaymentInitiator:
        gateway_name = str(gateway_name).upper()
        if gateway_name == PaymentGatewayChoice.PAYPAL:
            return self._build_paypal_gateway()
        if gateway_name == PaymentGatewayChoice.VIETQR:
            return VietQRService()
        raise UnsupportedPaymentCapability(f"Unsupported payment initiator: {gateway_name}")

    def get_payment_capturer(self, gateway_name: str) -> PaymentCapturer:
        gateway_name = str(gateway_name).upper()
        if gateway_name == PaymentGatewayChoice.PAYPAL:
            return self._build_paypal_gateway()
        raise UnsupportedPaymentCapability(f"{gateway_name} does not support payment capture")

    def get_refund_processor(self, gateway_name: str) -> RefundProcessor:
        gateway_name = str(gateway_name).upper()
        if gateway_name == PaymentGatewayChoice.PAYPAL:
            return self._build_paypal_gateway()
        raise UnsupportedPaymentCapability(f"{gateway_name} does not support automatic refunds")

    def _build_paypal_gateway(self) -> PayPalGateway:
        return PayPalGateway(
            client_id=settings.PAYPAL_CLIENT_ID,
            client_secret=settings.PAYPAL_CLIENT_SECRET,
            sandbox=getattr(settings, "PAYPAL_SANDBOX", True),
        )
