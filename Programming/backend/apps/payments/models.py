"""
Class: PaymentTransaction

Coupling Level:
- Data Coupling with PaymentService because PaymentService passes only the
  primitive values required to create/update a transaction record
  (order_id, transaction_id, amount, currency, status, gateway).
- Common Coupling (acceptable, Django ORM pattern) with the database layer
  via Django's ORM. This is standard and unavoidable in Django projects;
  the model does not share mutable global state in a problematic way.

Cohesion Level:
- Communicational Cohesion because all fields in this model exist to
  represent and persist a single payment transaction record. The class works
  on the same data object (the transaction) across all its operations.
  This is an acceptable level for a data/model class.

Reason:
PaymentTransaction is intentionally designed to be gateway-agnostic.
The `gateway` field stores which provider processed the payment (PAYPAL,
VIETQR) without hard-coding any provider-specific structure. This allows
the same model to represent transactions from any supported gateway.
"""

from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.orders.models import Order


class PaymentGatewayChoice(models.TextChoices):
    PAYPAL = "PAYPAL", "PayPal"
    VIETQR = "VIETQR", "VietQR"


class PaymentStatusChoice(models.TextChoices):
    PENDING = "PENDING", "Pending"
    SUCCESS = "SUCCESS", "Success"
    FAILED = "FAILED", "Failed"
    REFUNDED = "REFUNDED", "Refunded"
    CANCELLED = "CANCELLED", "Cancelled"


class RefundStatusChoice(models.TextChoices):
    PENDING = "PENDING", "Pending"
    SUCCESS = "SUCCESS", "Success"
    FAILED = "FAILED", "Failed"
    MANUAL_REQUIRED = "MANUAL_REQUIRED", "Manual required"


class RefundMethodChoice(models.TextChoices):
    PAYPAL_API = "PAYPAL_API", "PayPal API"
    MANUAL_BANK_TRANSFER = "MANUAL_BANK_TRANSFER", "Manual bank transfer"


# /*
#  * SOLID Review
#  * Principle: OCP/LSP
#  * Reason: PaymentTransaction is gateway-agnostic but still carries provider-specific fields such as provider_payload, capture_id, refund_id, and transaction_reference in one model.
#  * Impact: New payment methods may require nullable or overloaded fields, making transaction behavior harder to substitute consistently across providers.
#  * Improvement: Keep common transaction fields here and move provider-specific metadata into typed extension records or provider DTO serializers.
#  */
class PaymentTransaction(models.Model):
    """
    Records a payment transaction for an AIMS order.
    Gateway-agnostic: supports PayPal and VietQR (and future providers).

    Coupling Level:
    - Data Coupling with services: stores primitive fields used across layers.
    - Stamp Coupling (acceptable): views load ORM objects to call update
      helpers like mark_completed/mark_refunded.

    Cohesion Level:
    - Communicational Cohesion: all fields represent a single transaction record.

    Reason:
    - Keeping a gateway-agnostic model avoids schema duplication per provider
      and centralizes transaction lifecycle helpers on the model class.
    """

    order = models.ForeignKey(
        Order,
        on_delete=models.PROTECT,
        related_name="payments",
        help_text="The AIMS order this payment settles.",
    )
    gateway = models.CharField(
        max_length=20,
        choices=PaymentGatewayChoice.choices,
    )
    provider_order_id = models.CharField(
        max_length=128,
        blank=True,
        help_text="The order/payment ID returned by the payment provider (e.g. PayPal order ID).",
    )
    transaction_reference = models.CharField(
        max_length=64,
        blank=True,
        db_index=True,
        help_text="Provider-side reference used to match callbacks (e.g. VietQR content code). Blank for PayPal.",
    )
    provider_payload = models.JSONField(
        default=dict,
        blank=True,
        help_text="Provider-specific extra data (e.g. VietQR qr_payload/qr_image_url). Gateway-agnostic JSON.",
    )
    capture_id = models.CharField(
        max_length=128,
        blank=True,
        help_text="The capture ID returned after a successful payment capture. Used for refunds.",
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=10, default="VND")
    status = models.CharField(
        max_length=20,
        choices=PaymentStatusChoice.choices,
        default=PaymentStatusChoice.PENDING,
    )
    refund_id = models.CharField(
        max_length=128,
        blank=True,
        help_text="The refund ID from the payment provider after a successful refund.",
    )
    transaction_content = models.TextField(
        blank=True,
        help_text="Human-readable payment content/description (e.g. VietQR transfer content).",
    )
    transaction_datetime = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    note = models.TextField(blank=True)

    class Meta:
        ordering = ["-transaction_datetime"]
        verbose_name = "Payment Transaction"
        constraints = [
            models.CheckConstraint(
                name="ck_payment_transactions_amount_non_negative",
                condition=Q(amount__gte=0),
            ),
        ]

    def __str__(self):
        return f"[{self.gateway}] Order {self.order_id} — {self.status} — {self.amount} {self.currency}"

    def mark_success(self, capture_id: str = "") -> None:
        if capture_id:
            self.capture_id = capture_id
        self.status = PaymentStatusChoice.SUCCESS
        self.save(update_fields=["capture_id", "status", "updated_at"])

    def mark_refunded(self, refund_id: str) -> None:
        self.refund_id = refund_id
        self.status = PaymentStatusChoice.REFUNDED
        self.save(update_fields=["refund_id", "status", "updated_at"])

    def mark_failed(self, note: str = "") -> None:
        self.status = PaymentStatusChoice.FAILED
        if note:
            self.note = note
        self.save(update_fields=["status", "note", "updated_at"])


class RefundTransaction(models.Model):
    """
    Records a refund issued against a PaymentTransaction.

    Cohesion Level:
    - Communicational Cohesion: all fields describe a single refund record.

    Reason:
    - Matches the approved data model (refund_transactions): persists refund
      outcome, method, and the manual note required for manual bank transfers
      (VietQR has no automated refund).
    """

    payment_transaction = models.ForeignKey(
        PaymentTransaction,
        on_delete=models.PROTECT,
        related_name="refunds",
    )
    refund_amount = models.DecimalField(max_digits=14, decimal_places=2)
    refund_reason = models.TextField()
    refund_status = models.CharField(
        max_length=20,
        choices=RefundStatusChoice.choices,
        default=RefundStatusChoice.PENDING,
    )
    refund_method = models.CharField(
        max_length=24,
        choices=RefundMethodChoice.choices,
    )
    manual_refund_note = models.TextField(blank=True)
    processed_by = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        related_name="processed_refunds",
        null=True,
        blank=True,
        help_text="Manager who confirmed the manual refund.",
    )
    processed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                name="ck_refund_transactions_amount_non_negative",
                condition=Q(refund_amount__gte=0),
            ),
            models.CheckConstraint(
                name="ck_refund_transactions_manual_note_required",
                condition=~Q(refund_method=RefundMethodChoice.MANUAL_BANK_TRANSFER)
                | ~Q(manual_refund_note=""),
            ),
        ]

    def __str__(self):
        return f"Refund {self.refund_amount} ({self.refund_status}) for tx {self.payment_transaction_id}"

    def mark_manually_refunded(self, manager, note: str = "") -> None:
        """Confirm a manual (VietQR bank-transfer) refund as completed by a manager."""
        self.refund_status = RefundStatusChoice.SUCCESS
        self.processed_by = manager
        self.processed_at = timezone.now()
        if note:
            self.manual_refund_note = (
                f"{self.manual_refund_note}\n[Manual refund confirmed] {note}".strip()
            )
        self.save(
            update_fields=[
                "refund_status",
                "processed_by",
                "processed_at",
                "manual_refund_note",
            ]
        )
