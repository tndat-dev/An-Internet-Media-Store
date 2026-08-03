"""
Class: InitiatePayPalPaymentSerializer, CapturePayPalPaymentSerializer,
       PaymentTransactionSerializer

Coupling Level:
- Data Coupling with PaymentView because serializers receive only the HTTP
  request data dict and return validated primitive values — no large model
  objects are passed between view and serializer.
- Data Coupling with PaymentTransaction model (read serializer) because
  PaymentTransactionSerializer reads only the fields needed for the response.

Cohesion Level:
- Functional Cohesion because each serializer class has a single purpose:
  validate and deserialize one specific request type, or serialize one
  response type.

Reason:
Keeping request validation in serializers (not in views or services) follows
Django REST Framework conventions and keeps PaymentView thin. Each serializer
is responsible for exactly one data contract.
"""

from decimal import Decimal

from rest_framework import serializers

from .models import PaymentTransaction


class InitiatePayPalPaymentSerializer(serializers.Serializer):
    """Validates the request body for initiating a PayPal payment.

    Coupling Level:
    - Data Coupling with views: accepts primitive request fields only.

    Cohesion Level:
    - Functional Cohesion: single responsibility — validate initiate request.

    Reason:
    - Keeps validation logic out of views/services and defines a clear data
      contract for the initiate endpoint.
    """
    order_id = serializers.CharField(max_length=64)
    amount = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0.01"),
        required=False,
    )
    currency = serializers.CharField(max_length=10, default="USD")
    return_url = serializers.URLField()
    cancel_url = serializers.URLField()
    description = serializers.CharField(max_length=255, required=False, default="")


class CapturePayPalPaymentSerializer(serializers.Serializer):
    """Validates the request body for capturing an approved PayPal payment.

    Coupling Level:
    - Data Coupling with views: receives provider/internal IDs as primitives.

    Cohesion Level:
    - Functional Cohesion: validates only capture-related fields.

    Reason:
    - Keeps capture endpoint contract explicit and simple.
    """
    provider_order_id = serializers.CharField(max_length=128)
    internal_order_id = serializers.CharField(max_length=64)


class RefundPaymentSerializer(serializers.Serializer):
    """Validates the request body for issuing a refund.

    Coupling Level:
    - Data Coupling with views and RefundService: carries refund primitives.

    Cohesion Level:
    - Functional Cohesion: single-purpose validation for refund requests.

    Reason:
    - Centralizes refund validation and prevents business logic in views.
    """
    order_id = serializers.CharField(max_length=64)
    capture_id = serializers.CharField(max_length=128)
    amount = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0.01"),
    )
    currency = serializers.CharField(max_length=10, default="USD")
    reason = serializers.CharField(max_length=255, required=False, default="Customer cancelled order")


class PaymentTransactionSerializer(serializers.ModelSerializer):
    """Read-only serializer for returning transaction details to the client.

    Coupling Level:
    - Data Coupling with views: presents a read-only view of the ORM model.

    Cohesion Level:
    - Functional Cohesion: only serializes transaction fields for responses.

    Reason:
    - Keeps presentation concerns separate and prevents accidental updates
      from API responses.
    """

    order_id = serializers.UUIDField(source="order.order_id", read_only=True)

    class Meta:
        model = PaymentTransaction
        fields = [
            "id",
            "order_id",
            "gateway",
            "provider_order_id",
            "capture_id",
            "amount",
            "currency",
            "status",
            "refund_id",
            "transaction_datetime",
        ]
        read_only_fields = fields


class CreateVietQRPaymentSerializer(serializers.Serializer):
    """Validates the request body for creating a VietQR QR payment.

    Cohesion Level:
    - Functional Cohesion: single responsibility — validate the qr-code request.
    """
    order_id = serializers.CharField(max_length=64)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)


class VietQRTestCallbackSerializer(serializers.Serializer):
    """Validates a request to trigger VietQR sandbox Test Callback."""
    transaction_id = serializers.IntegerField(min_value=1)


class VietQRPaymentSerializer(serializers.Serializer):
    """Serializes a VietQR PaymentTransaction into the frontend payment DTO,
    including the QR payload/image and the frontend-facing status vocabulary.
    """

    def to_representation(self, instance: PaymentTransaction) -> dict:
        payload = instance.provider_payload or {}
        return {
            "transaction_id": str(instance.id),
            "order_id": str(instance.order_id),
            "order_token": str(instance.order.order_view_token),
            "order_status": instance.order.status,
            "payment_method": instance.gateway,
            "status": instance.status,
            "amount": f"{instance.amount:.2f}",
            "currency": instance.currency,
            "transaction_reference": instance.transaction_reference,
            "qr_payload": payload.get("qr_payload", ""),
            "qr_image_url": payload.get("qr_image_url", ""),
            "qr_code": payload.get("qr_code", ""),
            "qr_link": payload.get("qr_link", ""),
        }


class PaymentStatusSerializer(serializers.Serializer):
    """Serializes a PaymentTransaction status snapshot for the status endpoint."""

    def to_representation(self, instance: PaymentTransaction) -> dict:
        return {
            "transaction_id": str(instance.id),
            "order_id": str(instance.order_id),
            "order_token": str(instance.order.order_view_token),
            "order_status": instance.order.status,
            "payment_method": instance.gateway,
            "status": instance.status,
            "amount": f"{instance.amount:.2f}",
            "currency": instance.currency,
            "transaction_reference": instance.transaction_reference,
        }
