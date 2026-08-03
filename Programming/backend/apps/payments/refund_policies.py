from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.orders import notifications
from apps.orders.models import Order, OrderStatus

from .lifecycle_service import PaymentLifecycleService
from .models import (
    PaymentGatewayChoice,
    PaymentTransaction,
    RefundMethodChoice,
    RefundStatusChoice,
    RefundTransaction,
)
from .provider_registry import PaymentProviderRegistry
from .refund_service import RefundRequest, RefundService


def _money(value: Decimal) -> Decimal:
    return Decimal(value).quantize(Decimal("0.01"))


@dataclass(frozen=True)
class RefundExecutionContext:
    order: Order
    payment_transaction: PaymentTransaction
    reason: str
    internal_refund_amount: Decimal


class RefundPolicy(ABC):
    action_code = "UNKNOWN"

    @abstractmethod
    def apply(self, context: RefundExecutionContext) -> str:
        """Execute or record the refund action for a paid order."""


class PayPalAutoRefundPolicy(RefundPolicy):
    action_code = "AUTO_REFUND"

    def __init__(
        self,
        provider_registry: PaymentProviderRegistry | None = None,
        lifecycle_service: PaymentLifecycleService | None = None,
    ):
        self._provider_registry = provider_registry or PaymentProviderRegistry()
        self._lifecycle_service = lifecycle_service or PaymentLifecycleService()

    def apply(self, context: RefundExecutionContext) -> str:
        tx = context.payment_transaction
        refund_processor = self._provider_registry.get_refund_processor(tx.gateway)
        response = RefundService(refund_processor=refund_processor).refund_order(
            RefundRequest(
                order_id=str(context.order.order_id),
                capture_id=tx.capture_id,
                amount=float(self._provider_refund_amount(tx)),
                currency=self._provider_refund_currency(tx),
                reason=context.reason,
            )
        )
        if response.success:
            self._lifecycle_service.mark_refunded(
                tx,
                refund_id=response.refund_id or "",
            )
            RefundTransaction.objects.create(
                payment_transaction=tx,
                refund_amount=context.internal_refund_amount,
                refund_reason=context.reason,
                refund_status=RefundStatusChoice.SUCCESS,
                refund_method=RefundMethodChoice.PAYPAL_API,
            )
            return self.action_code

        RefundTransaction.objects.create(
            payment_transaction=tx,
            refund_amount=context.internal_refund_amount,
            refund_reason=context.reason,
            refund_status=RefundStatusChoice.FAILED,
            refund_method=RefundMethodChoice.PAYPAL_API,
        )
        raise ValidationError(
            {
                "refund": (
                    response.error_message
                    or "PayPal refund failed. The order was not cancelled or rejected."
                )
            }
        )

    def _provider_refund_amount(self, payment_transaction: PaymentTransaction) -> Decimal:
        payload = payment_transaction.provider_payload or {}
        raw_amount = (
            payload.get("paypal_captured_amount")
            or payload.get("paypal_amount")
            or payment_transaction.amount
        )
        return _money(Decimal(str(raw_amount)))

    def _provider_refund_currency(self, payment_transaction: PaymentTransaction) -> str:
        payload = payment_transaction.provider_payload or {}
        return str(payload.get("paypal_currency") or payment_transaction.currency).upper()


class ManualRefundPolicy(RefundPolicy):
    action_code = "MANUAL_REFUND_REQUIRED"

    def apply(self, context: RefundExecutionContext) -> str:
        RefundTransaction.objects.create(
            payment_transaction=context.payment_transaction,
            refund_amount=context.internal_refund_amount,
            refund_reason=context.reason,
            refund_status=RefundStatusChoice.MANUAL_REQUIRED,
            refund_method=RefundMethodChoice.MANUAL_BANK_TRANSFER,
            manual_refund_note=(
                "VietQR has no automated refund API; a manager must process "
                "this refund manually."
            ),
        )
        transaction.on_commit(
            lambda: notifications.send_manual_refund_notice(
                context.order,
                context.internal_refund_amount,
            )
        )
        return self.action_code


class RefundPolicyRegistry:
    """Central resolver for provider-specific refund behavior."""

    def __init__(self, provider_registry: PaymentProviderRegistry | None = None):
        self._provider_registry = provider_registry or PaymentProviderRegistry()

    def resolve_policy(self, gateway_name: str) -> RefundPolicy:
        gateway_name = str(gateway_name).upper()
        if gateway_name == PaymentGatewayChoice.PAYPAL:
            return PayPalAutoRefundPolicy(provider_registry=self._provider_registry)
        if gateway_name == PaymentGatewayChoice.VIETQR:
            return ManualRefundPolicy()
        raise ValidationError({"refund": f"Unsupported payment method: {gateway_name}"})

    def determine_action(self, order_status: str, payment_method: str) -> str:
        if order_status not in {status.value for status in OrderStatus}:
            return "INVALID_ORDER_STATUS"
        if payment_method not in {choice for choice, _ in PaymentGatewayChoice.choices}:
            return "INVALID_PAYMENT_METHOD"
        if order_status != OrderStatus.PENDING_PROCESSING:
            return "NOT_REFUNDABLE_BY_CUSTOMER_CANCEL"
        return self.resolve_policy(payment_method).action_code


class PaymentRefundCoordinator:
    """Payment-side orchestrator for refund policy selection and execution."""

    def __init__(self, policy_registry: RefundPolicyRegistry | None = None):
        self._policy_registry = policy_registry or RefundPolicyRegistry()

    def issue_refund(
        self,
        *,
        order: Order,
        payment_transaction: PaymentTransaction,
        reason: str,
        internal_refund_amount: Decimal,
    ) -> str:
        context = RefundExecutionContext(
            order=order,
            payment_transaction=payment_transaction,
            reason=reason,
            internal_refund_amount=internal_refund_amount,
        )
        policy = self._policy_registry.resolve_policy(payment_transaction.gateway)
        return policy.apply(context)
