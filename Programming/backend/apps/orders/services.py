import logging
from decimal import Decimal
from math import ceil

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.carts.models import CartStatus
from apps.carts.services import CartService
from apps.orders import notifications
from apps.orders.models import DeliveryInfo, Invoice, Order, OrderItem, OrderStatus
from apps.orders.provinces import normalize_province, resolve_region
from apps.orders.validators import DeliveryInfoValidator
from apps.products.models import Product

logger = logging.getLogger(__name__)


class InsufficientStockError(ValidationError):
    """Raised when an order cannot be fulfilled because stock ran out.

    Subclasses Django's ValidationError so the orders views map it to HTTP 400
    automatically; the payment seam catches it explicitly (see mark_order_paid).
    """


class DetailedValidationError(Exception):
    """Raised when the API must preserve a structured validation payload."""

    def __init__(self, payload: dict):
        super().__init__("Detailed validation error")
        self.payload = payload


def can_cancel_order(order_status: str) -> bool:
    return order_status == OrderStatus.PENDING_PROCESSING


# /*
#  * SOLID Review
#  * Principle: OCP
#  * Reason: determine_refund_action uses explicit payment_method branches to decide refund behavior for PayPal and VietQR.
#  * Impact: Adding a new payment provider or refund policy requires modifying this function and retesting existing provider decisions.
#  * Improvement: Move refund decision rules into provider-specific policy classes registered by payment method.
#  */
def determine_refund_action(order_status: str, payment_method: str) -> str:
    from apps.payments.refund_policies import RefundPolicyRegistry

    return RefundPolicyRegistry().determine_action(order_status, payment_method)


def calculate_delivery_fee(province: str, weight_kg: Decimal, order_value: Decimal) -> int:
    if weight_kg <= 0:
        raise ValueError("weight_kg must be greater than 0")
    if order_value < 0:
        raise ValueError("order_value must not be negative")

    normalized_province = normalize_province(province)
    resolve_region(normalized_province)
    if normalized_province in {"Ha Noi", "Ho Chi Minh City"}:
        base_fee = 22000
        base_weight = Decimal("3.0")
    else:
        base_fee = 30000
        base_weight = Decimal("0.5")

    fee = base_fee
    if weight_kg > base_weight:
        extra_weight = weight_kg - base_weight
        extra_units = ceil(extra_weight / Decimal("0.5"))
        fee += extra_units * 2500

    if order_value > Decimal("100000"):
        fee = max(0, fee - 25000)

    return int(fee)


def _money(value: Decimal) -> Decimal:
    return Decimal(value).quantize(Decimal("0.01"))


# /*
#  * SOLID Review
#  * Principle: OCP
#  * Reason: DeliveryFeeService delegates to a hard-coded city/weight/discount formula that must change for new shipping regions or fee rules.
#  * Impact: Shipping-rule changes can ripple through checkout tests and make fee calculation less extensible.
#  * Improvement: Introduce delivery fee policy objects or configurable rate tables selected by province/method.
#  */
class DeliveryFeeService:
    """
    Coupling/Cohesion: contains only shipping-fee rules. It depends on scalar
    province, weight, and order value inputs, not on HTTP requests or models.
    """

    @staticmethod
    def calculate(province: str, weight_kg: Decimal, order_value: Decimal) -> Decimal:
        billable_weight = weight_kg if weight_kg > 0 else Decimal("0.5")
        return Decimal(calculate_delivery_fee(province, billable_weight, order_value))


class InvoiceService:
    """
    Coupling/Cohesion: owns invoice math and persistence. It reads order item
    snapshots and delivery fee, but does not validate delivery fields or payment.
    """

    VAT_RATE = Decimal("0.10")

    @classmethod
    def build_totals(cls, order: Order, delivery_fee: Decimal) -> dict[str, Decimal]:
        subtotal = sum((item.line_amount_excl_vat for item in order.items.all()), Decimal("0.00"))
        vat_amount = _money(subtotal * cls.VAT_RATE)
        total_incl_vat = _money(subtotal + vat_amount)
        final_total = _money(total_incl_vat + delivery_fee)
        return {
            "total_product_price_excl_vat": _money(subtotal),
            "vat_amount": vat_amount,
            "total_product_price_incl_vat": total_incl_vat,
            "delivery_fee": _money(delivery_fee),
            "total_amount_to_pay": final_total,
        }

    @classmethod
    def upsert_invoice(cls, order: Order, delivery_fee: Decimal) -> Invoice:
        totals = cls.build_totals(order, delivery_fee)
        invoice, _ = Invoice.objects.update_or_create(order=order, defaults=totals)
        order.total_amount = invoice.total_amount_to_pay
        order.save(update_fields=["total_amount", "updated_at"])
        return invoice


# /*
#  * SOLID Review
#  * Principle: SRP/DIP
#  * Reason: OrderPlacementService orchestrates order creation, cart validation, delivery persistence, invoice creation, fulfillment, stock mutation, notifications, and refund execution.
#  * Impact: The class has many reasons to change and directly imports concrete payment classes in refund paths, reducing maintainability and test isolation.
#  * Improvement: Keep order placement orchestration but inject refund/payment, notification, stock, and persistence collaborators behind abstractions.
#  */
class OrderPlacementService:
    """
    Coupling/Cohesion: orchestrates Place Order by delegating cart validation,
    delivery validation, fee calculation, and invoice math to focused services.
    Views call this service instead of embedding the business sequence.
    """

    @staticmethod
    def _get_order(order_id: str) -> Order:
        return Order.objects.prefetch_related("items").get(order_id=order_id)

    @staticmethod
    def _refresh_order_items(order: Order) -> None:
        cart = CartService.get_cart(order.cart.cart_token)
        OrderItem.objects.filter(order=order).delete()
        for cart_item in cart.items.select_related("product"):
            unit_price = _money(cart_item.product.current_price)
            line_excl_vat = _money(unit_price * cart_item.quantity)
            line_incl_vat = _money(line_excl_vat * Decimal("1.10"))
            OrderItem.objects.create(
                order=order,
                product=cart_item.product,
                product_title=cart_item.product.title,
                unit_price=unit_price,
                quantity=cart_item.quantity,
                line_amount_excl_vat=line_excl_vat,
                line_amount_incl_vat=line_incl_vat,
            )

    @staticmethod
    def _cart_matches_order(order: Order) -> bool:
        cart = CartService.get_cart(order.cart.cart_token)
        cart_items = {
            str(item.product.product_id): item.quantity
            for item in cart.items.select_related("product")
        }
        order_items = {
            str(item.product.product_id): item.quantity
            for item in order.items.select_related("product")
        }
        return cart_items == order_items

    @staticmethod
    @transaction.atomic
    def create_draft_order(cart_token: str) -> Order:
        cart = CartService.get_cart(cart_token)
        stock_errors = CartService.validate_cart_for_checkout(cart)
        if stock_errors:
            raise DetailedValidationError({"cart": stock_errors})

        order = (
            Order.objects.filter(cart=cart, status=OrderStatus.PENDING_PAYMENT)
            .order_by("-created_at")
            .first()
        )
        if order is None:
            order = Order.objects.create(cart=cart, status=OrderStatus.PENDING_PAYMENT)
        else:
            DeliveryInfo.objects.filter(order=order).delete()
            Invoice.objects.filter(order=order).delete()

        OrderPlacementService._refresh_order_items(order)
        subtotal = sum((item.line_amount_incl_vat for item in order.items.all()), Decimal("0.00"))
        order.total_amount = _money(subtotal)
        order.save(update_fields=["total_amount", "updated_at"])
        return OrderPlacementService._get_order(str(order.order_id))

    @staticmethod
    @transaction.atomic
    def apply_delivery_info(order_id: str, delivery_info: dict) -> Order:
        order = OrderPlacementService._get_order(order_id)
        if order.status != OrderStatus.PENDING_PAYMENT:
            raise ValidationError({"order": "Only pending-payment orders can update delivery info."})

        validation = DeliveryInfoValidator.validate(delivery_info)
        if not validation["valid"]:
            raise ValidationError(validation["errors"])

        cart = CartService.get_cart(order.cart.cart_token)
        stock_errors = CartService.validate_cart_for_checkout(cart)
        if stock_errors:
            raise DetailedValidationError({"cart": stock_errors})

        OrderPlacementService._refresh_order_items(order)
        order = OrderPlacementService._get_order(str(order.order_id))
        subtotal_excl_vat = sum((item.line_amount_excl_vat for item in order.items.all()), Decimal("0.00"))
        delivery_fee = DeliveryFeeService.calculate(
            province=delivery_info["province"],
            weight_kg=CartService.total_weight_kg(cart),
            order_value=subtotal_excl_vat,
        )

        DeliveryInfo.objects.update_or_create(
            order=order,
            defaults={
                "customer_name": delivery_info["name"].strip(),
                "phone_number": delivery_info["phone"].strip(),
                "email": delivery_info["email"].strip(),
                "delivery_province": delivery_info["province"].strip(),
                "delivery_address": delivery_info["address"].strip(),
                "delivery_method": delivery_info.get("delivery_method", "STANDARD").strip().upper(),
                "delivery_instructions": delivery_info.get("delivery_instructions", "").strip(),
                "shipping_fee": delivery_fee,
            },
        )
        InvoiceService.upsert_invoice(order, delivery_fee)
        return OrderPlacementService._get_order(str(order.order_id))

    @staticmethod
    def preview_delivery(order_id: str, province: str, delivery_method: str = "") -> dict[str, Decimal]:
        """Compute delivery fee + totals for a province WITHOUT persisting, so the
        delivery screen can show a live Order Summary. Fee is weight-based (the
        Standard/Express choice does not change the fee per the shipping rule)."""
        order = OrderPlacementService._get_order(order_id)
        subtotal_excl_vat = sum(
            (item.line_amount_excl_vat for item in order.items.all()), Decimal("0.00")
        )
        weight = (
            CartService.total_weight_kg(CartService.get_cart(order.cart.cart_token))
            if order.cart_id
            else Decimal("0.5")
        )
        delivery_fee = DeliveryFeeService.calculate(
            province=province, weight_kg=weight, order_value=subtotal_excl_vat
        )
        return InvoiceService.build_totals(order, delivery_fee)

    @staticmethod
    def get_invoice(order_id: str) -> Invoice:
        return Invoice.objects.select_related("order", "order__delivery_info").prefetch_related("order__items").get(order_id=order_id)

    @staticmethod
    @transaction.atomic
    def confirm_order(order_id: str) -> Order:
        order = OrderPlacementService._get_order(order_id)
        if order.status != OrderStatus.PENDING_PAYMENT:
            raise ValidationError({"order": "Order is not pending payment."})
        if not hasattr(order, "delivery_info"):
            raise ValidationError({"delivery": "Delivery information is required."})
        if not hasattr(order, "invoice"):
            raise ValidationError({"invoice": "Invoice is required."})

        cart = CartService.get_cart(order.cart.cart_token)
        stock_errors = CartService.validate_cart_for_checkout(cart)
        if stock_errors:
            raise DetailedValidationError({"cart": stock_errors})
        if not OrderPlacementService._cart_matches_order(order):
            raise ValidationError({"cart": "Cart changed after invoice. Please recreate the draft order."})

        cart.status = CartStatus.CHECKED_OUT
        cart.save(update_fields=["status", "updated_at"])
        order.updated_at = timezone.now()
        order.save(update_fields=["updated_at"])
        return OrderPlacementService._get_order(str(order.order_id))

    @staticmethod
    def _restore_stock(order: Order) -> None:
        """Return reserved stock to inventory when a paid order is cancelled/rejected."""
        for item in order.items.all():
            Product.objects.filter(product_id=item.product_id).update(
                stock_quantity=F("stock_quantity") + item.quantity
            )

    @staticmethod
    def _refund_amount_vnd(order: Order) -> Decimal:
        invoice = getattr(order, "invoice", None)
        if invoice is not None:
            return _money(invoice.total_amount_to_pay)
        return _money(order.total_amount)

    @staticmethod
    def _issue_refund(order: Order) -> str:
        """orders <-> payments boundary: decide and issue a refund for a paid order
        that is being cancelled/rejected.

        Refund EXECUTION belongs to the payment subsystem (owned by the payment
        teammates); orders only decides *when* a refund is due and records the
        outcome. Call this while the order is still PENDING_PROCESSING (before
        flipping to CANCELLED/REJECTED), because determine_refund_action gates on it.

        Returns the refund action taken, or "NO_PAYMENT" if nothing to refund.
        """
        # Local imports keep apps.orders import-time independent of apps.payments.
        from apps.payments.models import (
            PaymentStatusChoice,
            PaymentTransaction,
        )
        from apps.payments.refund_policies import PaymentRefundCoordinator

        tx = (
            PaymentTransaction.objects.filter(order=order, status=PaymentStatusChoice.SUCCESS)
            .order_by("-transaction_datetime")
            .first()
        )
        if tx is None:
            return "NO_PAYMENT"

        action = determine_refund_action(order.status, tx.gateway)
        reason = "Order cancelled/rejected before approval"
        internal_refund_amount = OrderPlacementService._refund_amount_vnd(order)
        if action in {"AUTO_REFUND", "MANUAL_REFUND_REQUIRED"}:
            return PaymentRefundCoordinator().issue_refund(
                order=order,
                payment_transaction=tx,
                reason=reason,
                internal_refund_amount=internal_refund_amount,
            )

        return action

    @staticmethod
    @transaction.atomic
    def mark_order_paid(order_id: str) -> Order:
        """Fulfill an order after a successful payment: transition to
        PENDING_PROCESSING, decrement stock, and clear the cart.

        Single fulfillment entrypoint for both the manual /mark-paid/ endpoint and
        the payment success callbacks (VietQR callback / PayPal capture), so there
        is exactly one idempotency surface.

        Idempotent: the status gate runs first, so stock is decremented only on the
        unique PENDING_PAYMENT -> PENDING_PROCESSING edge. A retried callback finds
        the order already PENDING_PROCESSING and returns without double-decrementing.
        """
        order = Order.objects.select_for_update().get(order_id=order_id)
        if order.status == OrderStatus.PENDING_PROCESSING:
            return OrderPlacementService._get_order(str(order.order_id))
        if order.status != OrderStatus.PENDING_PAYMENT:
            raise ValidationError({"order": "Order is not awaiting payment."})

        # Decrement with an oversell guard: the conditional filter means two orders
        # racing for the last unit are serialized by the DB; the loser gets
        # updated == 0 and the whole atomic block rolls back.
        for item in order.items.all():
            updated = Product.objects.filter(
                product_id=item.product_id,
                stock_quantity__gte=item.quantity,
            ).update(stock_quantity=F("stock_quantity") - item.quantity)
            if updated == 0:
                raise InsufficientStockError(
                    {"stock": f"Insufficient stock to fulfill '{item.product_title}'."}
                )

        if order.cart_id is not None:
            CartService.clear(order.cart)

        order.status = OrderStatus.PENDING_PROCESSING
        order.updated_at = timezone.now()
        order.save(update_fields=["status", "updated_at"])
        fulfilled = OrderPlacementService._get_order(str(order.order_id))
        transaction.on_commit(lambda: notifications.send_order_confirmation(fulfilled))
        return fulfilled


def fulfill_paid_order(order_id: str) -> None:
    """Payment -> orders integration seam.

    Called by the payment success paths (VietQR callback, PayPal capture) right
    after the gateway confirms payment. This is the boundary between the payment
    subsystem (owned by the payment teammates) and order fulfillment (Place Order).

    Non-raising on purpose: the customer has already paid, so a failure here must
    not turn the callback into a 5xx. The two expected failures are swallowed:
      - InsufficientStockError: a rare paid-but-unfulfillable race (stock vanished);
        logged and left as PENDING_PAYMENT for manual resolution by a manager.
      - ValidationError: the order is not awaiting payment (already processed),
        which means there is nothing to do.
    Any other (unexpected) error is allowed to propagate so it stays visible.
    """
    try:
        OrderPlacementService.mark_order_paid(order_id)
    except InsufficientStockError:
        logger.warning(
            "Paid order %s could not be fulfilled: insufficient stock. "
            "Order left PENDING_PAYMENT for manual resolution.",
            order_id,
        )
        transaction.on_commit(
            lambda: notifications.send_unfulfillable_paid_order_notice(order_id)
        )
    except ValidationError:
        logger.info("fulfill_paid_order: order %s is not awaiting payment; skipping.", order_id)


class OrderCancellationService:
    """Customer-initiated cancellation of a paid order before manager approval.

    Coupling/Cohesion: owns the cancel workflow only, reusing OrderPlacementService
    stock/refund helpers so cancel and manager-reject share one refund path.
    """

    @staticmethod
    @transaction.atomic
    def cancel_order(order: Order) -> Order:
        order = Order.objects.select_for_update().get(order_id=order.order_id)
        if not can_cancel_order(order.status):
            raise ValidationError({"order": "Order can no longer be cancelled."})

        OrderPlacementService._restore_stock(order)
        OrderPlacementService._issue_refund(order)  # while still PENDING_PROCESSING

        order.status = OrderStatus.CANCELLED
        order.updated_at = timezone.now()
        order.save(update_fields=["status", "updated_at"])
        cancelled = OrderPlacementService._get_order(str(order.order_id))
        transaction.on_commit(lambda: notifications.send_order_cancellation(cancelled))
        return cancelled


class OrderReviewService:
    """Manager order review: list the pending-processing queue, approve, reject.

    Coupling/Cohesion: owns the manager review workflow; reject reuses the shared
    stock-restore + refund helpers (reject == manager-initiated cancel).
    """

    @staticmethod
    def list_pending():
        return (
            Order.objects.filter(status=OrderStatus.PENDING_PROCESSING)
            .prefetch_related("items")
            .select_related("delivery_info", "invoice")
        )

    @staticmethod
    def get_order_detail(order_id: str) -> Order:
        return OrderPlacementService._get_order(order_id)

    @staticmethod
    def list_manual_refunds():
        """Cancelled/rejected orders whose refund must be handled manually (VietQR).

        orders <-> payments boundary: filters on the payments-side manual refund
        method via the reverse relations, mirroring _issue_refund's local-import
        boundary pattern. Returns both states so the manager can see what is still
        outstanding (MANUAL_REQUIRED/FAILED) and what was already paid (SUCCESS).
        """
        from apps.payments.models import RefundMethodChoice

        return (
            Order.objects.filter(
                status__in=[OrderStatus.CANCELLED, OrderStatus.REJECTED],
                payments__refunds__refund_method=RefundMethodChoice.MANUAL_BANK_TRANSFER,
            )
            .distinct()
            .prefetch_related("items", "payments__refunds")
            .select_related("delivery_info", "invoice")
            .order_by("-updated_at")
        )

    @staticmethod
    @transaction.atomic
    def mark_refund_complete(order_id: str, manager, note: str = "") -> Order:
        """Record that a manager has manually refunded a VietQR order.

        Flips the outstanding manual RefundTransaction to SUCCESS (with audit
        fields) and marks the underlying payment REFUNDED. Refund EXECUTION still
        happens outside the system (bank transfer); this only records the outcome.
        """
        from apps.payments.models import (
            RefundMethodChoice,
            RefundStatusChoice,
            RefundTransaction,
        )

        refund = (
            RefundTransaction.objects.select_for_update()
            .filter(
                payment_transaction__order_id=order_id,
                refund_method=RefundMethodChoice.MANUAL_BANK_TRANSFER,
                refund_status__in=[
                    RefundStatusChoice.MANUAL_REQUIRED,
                    RefundStatusChoice.FAILED,
                ],
            )
            .order_by("-created_at")
            .first()
        )
        if refund is None:
            raise ValidationError(
                {"refund": "No outstanding manual refund found for this order."}
            )

        refund.mark_manually_refunded(manager, note)

        tx = refund.payment_transaction
        from apps.payments.lifecycle_service import PaymentLifecycleService

        PaymentLifecycleService().mark_refunded(tx)

        return OrderPlacementService._get_order(str(order_id))

    @staticmethod
    @transaction.atomic
    def approve_order(order_id: str, manager) -> Order:
        order = Order.objects.select_for_update().get(order_id=order_id)
        if order.status != OrderStatus.PENDING_PROCESSING:
            raise ValidationError({"order": "Only pending-processing orders can be approved."})

        order.status = OrderStatus.APPROVED
        order.processed_by = manager
        order.processed_at = timezone.now()
        order.save(update_fields=["status", "processed_by", "processed_at", "updated_at"])
        approved = OrderPlacementService._get_order(str(order.order_id))
        transaction.on_commit(lambda: notifications.send_order_approved(approved))
        return approved

    @staticmethod
    @transaction.atomic
    def reject_order(order_id: str, manager, reason: str = "") -> Order:
        order = Order.objects.select_for_update().get(order_id=order_id)
        if order.status != OrderStatus.PENDING_PROCESSING:
            raise ValidationError({"order": "Only pending-processing orders can be rejected."})

        OrderPlacementService._restore_stock(order)
        OrderPlacementService._issue_refund(order)  # while still PENDING_PROCESSING

        order.status = OrderStatus.REJECTED
        order.processed_by = manager
        order.processed_at = timezone.now()
        order.save(update_fields=["status", "processed_by", "processed_at", "updated_at"])
        rejected = OrderPlacementService._get_order(str(order.order_id))
        transaction.on_commit(lambda: notifications.send_order_rejected(rejected, reason))
        return rejected
