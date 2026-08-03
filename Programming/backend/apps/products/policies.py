"""Deletion policy for product CUD use cases.

Extracted from ``ProductService.delete_products`` so the three independent rules —
per-request cap, per-manager daily cap, and the delete-vs-deactivate decision —
each have a single reason to change (SRP) and can be unit-tested without driving
the whole delete flow. ``ProductService`` keeps only orchestration.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.products.models import (
    Product,
    ProductHistory,
    ProductHistoryActionType,
    ProductStatus,
)


class DeletionPolicy:
    MAX_PER_REQUEST = 10
    MAX_PER_DAY = 20

    def check_request_size(self, count: int) -> None:
        if count > self.MAX_PER_REQUEST:
            raise ValidationError(
                {"product_ids": "Cannot delete more than 10 products per request."}
            )

    def check_daily_cap(self, *, manager_id: str, adding: int) -> None:
        today_count = ProductHistory.objects.filter(
            performed_by__username=manager_id,
            action_type__in=[ProductHistoryActionType.DELETE, ProductHistoryActionType.DEACTIVATE],
            created_at__date=timezone.localdate(),
        ).count()
        if today_count + adding > self.MAX_PER_DAY:
            raise ValidationError(
                {"product_ids": "Cannot delete more than 20 products per manager per day."}
            )

    def resolve_status(self, product: Product) -> tuple[str, str]:
        """Decide the post-delete status + audit action for one product.

        A product with zero stock is hard-marked DELETED; a product that still has
        stock is DEACTIVATED instead (stock-aware delete rule).
        """
        if product.stock_quantity == 0:
            return ProductStatus.DELETED, ProductHistoryActionType.DELETE
        return ProductStatus.DEACTIVATED, ProductHistoryActionType.DEACTIVATE
