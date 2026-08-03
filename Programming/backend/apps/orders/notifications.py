"""Order email notifications.

The orders app owns these customer/manager notification events (the payment
subsystem stays gateway-only). Every function is intentionally NON-FATAL: a mail
failure is logged and swallowed so it can never roll back order fulfillment or
turn a payment callback into a 5xx. Callers should fire these via
``transaction.on_commit(...)`` so mail is only sent once the state has persisted.

Currency/number formatting follows the UI spec ("1,000 VND").
"""

import logging
from decimal import Decimal

from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)


def _money(value) -> str:
    """Format a money value as the UI-standard '1,000 VND'."""
    try:
        amount = Decimal(value or 0).quantize(Decimal("1"))
    except (TypeError, ValueError):
        amount = Decimal("0")
    return f"{amount:,} VND"


def _customer_email(order) -> str | None:
    delivery = getattr(order, "delivery_info", None)
    email = getattr(delivery, "email", "") if delivery else ""
    return email or None


def _send(subject: str, body: str, recipient: str | None) -> None:
    """Send one plain-text email, swallowing all errors (non-fatal by design)."""
    if not recipient:
        logger.info("Skipping email '%s': no recipient address.", subject)
        return
    try:
        send_mail(
            subject=subject,
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient],
            fail_silently=False,
        )
    except Exception:  # noqa: BLE001 - notifications must never break the flow
        logger.exception("Failed to send email '%s' to %s", subject, recipient)


def send_order_confirmation(order) -> None:
    """Invoice + transaction confirmation to the customer after a paid order."""
    invoice = getattr(order, "invoice", None)
    lines = [
        f"Thank you! Your order {order.order_id} has been paid and is now Pending Processing.",
        "",
    ]
    if invoice is not None:
        lines += [
            f"Subtotal (excl. VAT): {_money(invoice.total_product_price_excl_vat)}",
            f"VAT (10%): {_money(invoice.vat_amount)}",
            f"Total (incl. VAT): {_money(invoice.total_product_price_incl_vat)}",
            f"Delivery fee: {_money(invoice.delivery_fee)}",
            f"Total paid: {_money(invoice.total_amount_to_pay)}",
        ]
    lines += [
        "",
        f"Track or cancel your order (before approval) using token: {order.order_view_token}",
    ]
    _send(f"AIMS order {order.order_id} confirmed", "\n".join(lines), _customer_email(order))


def send_order_cancellation(order) -> None:
    body = (
        f"Your order {order.order_id} has been cancelled. "
        "If you paid by card, a refund has been issued to your original payment method. "
        "VietQR payments are refunded manually by our team."
    )
    _send(f"AIMS order {order.order_id} cancelled", body, _customer_email(order))


def send_order_approved(order) -> None:
    body = f"Good news! Your order {order.order_id} has been approved and is being prepared for delivery."
    _send(f"AIMS order {order.order_id} approved", body, _customer_email(order))


def send_order_rejected(order, reason: str = "") -> None:
    body = f"We're sorry — your order {order.order_id} was rejected."
    if reason:
        body += f"\nReason: {reason}"
    body += "\nAny payment made will be refunded (card refunds are automatic; VietQR refunds are manual)."
    _send(f"AIMS order {order.order_id} rejected", body, _customer_email(order))


def send_manual_refund_notice(order, refund_amount) -> None:
    """Tell the manager a VietQR order needs a manual refund (no automated API)."""
    body = (
        f"Manual refund required for order {order.order_id}.\n"
        f"Amount: {_money(refund_amount)}\n"
        "VietQR has no automated refund API; please process this refund manually "
        "and update the refund transaction record."
    )
    _send(f"[ACTION] Manual refund required — order {order.order_id}", body, settings.AIMS_MANAGER_NOTICE_EMAIL)


def send_unfulfillable_paid_order_notice(order_id) -> None:
    """Tell the manager a paid order could not be fulfilled (stock ran out)."""
    body = (
        f"Order {order_id} was paid but could NOT be fulfilled because stock ran out "
        "between checkout and payment. The order is left PENDING_PAYMENT. Please review: "
        "either restock and re-run fulfillment, or refund the customer."
    )
    _send(f"[ACTION] Paid order unfulfillable — order {order_id}", body, settings.AIMS_MANAGER_NOTICE_EMAIL)
