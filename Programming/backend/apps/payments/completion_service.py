from __future__ import annotations

from typing import Any

from apps.orders.services import fulfill_paid_order

from .lifecycle_service import PaymentLifecycleService
from .models import PaymentTransaction


class PaymentCompletionService:
    """Completes a successful payment and triggers order fulfillment."""

    def __init__(
        self,
        lifecycle_service: PaymentLifecycleService | None = None,
    ) -> None:
        self._lifecycle_service = lifecycle_service or PaymentLifecycleService()

    def complete_successful_payment(
        self,
        transaction: PaymentTransaction,
        *,
        capture_id: str = "",
        provider_payload_patch: dict[str, Any] | None = None,
        note: str = "",
    ) -> PaymentTransaction:
        transaction = self._lifecycle_service.mark_success(
            transaction,
            capture_id=capture_id,
            provider_payload_patch=provider_payload_patch,
            note=note,
        )
        fulfill_paid_order(str(transaction.order_id))
        return transaction
