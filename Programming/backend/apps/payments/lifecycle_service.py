from __future__ import annotations

from typing import Any

from .models import PaymentStatusChoice, PaymentTransaction


class PaymentLifecycleService:
    """Centralizes PaymentTransaction state mutations for the payment module."""

    @staticmethod
    def _merged_provider_payload(
        current_payload: dict[str, Any] | None,
        provider_payload_patch: dict[str, Any] | None,
    ) -> dict[str, Any]:
        merged = dict(current_payload or {})
        if provider_payload_patch:
            merged.update(provider_payload_patch)
        return merged

    def mark_success(
        self,
        transaction: PaymentTransaction,
        *,
        capture_id: str = "",
        provider_payload_patch: dict[str, Any] | None = None,
        note: str = "",
    ) -> PaymentTransaction:
        update_fields = ["status", "updated_at"]
        transaction.status = PaymentStatusChoice.SUCCESS

        if capture_id:
            transaction.capture_id = capture_id
            update_fields.append("capture_id")

        if provider_payload_patch:
            transaction.provider_payload = self._merged_provider_payload(
                transaction.provider_payload,
                provider_payload_patch,
            )
            update_fields.append("provider_payload")

        if note:
            transaction.note = note
            update_fields.append("note")

        transaction.save(update_fields=update_fields)
        return transaction

    def mark_failed(
        self,
        transaction: PaymentTransaction,
        *,
        reason: str = "",
        provider_payload_patch: dict[str, Any] | None = None,
    ) -> PaymentTransaction:
        update_fields = ["status", "updated_at"]
        transaction.status = PaymentStatusChoice.FAILED

        if provider_payload_patch:
            transaction.provider_payload = self._merged_provider_payload(
                transaction.provider_payload,
                provider_payload_patch,
            )
            update_fields.append("provider_payload")

        if reason:
            transaction.note = reason
            update_fields.append("note")

        transaction.save(update_fields=update_fields)
        return transaction

    def mark_refunded(
        self,
        transaction: PaymentTransaction,
        *,
        refund_id: str = "",
    ) -> PaymentTransaction:
        update_fields = ["status", "updated_at"]
        transaction.status = PaymentStatusChoice.REFUNDED

        if refund_id:
            transaction.refund_id = refund_id
            update_fields.append("refund_id")

        transaction.save(update_fields=update_fields)
        return transaction
