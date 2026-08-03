from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.products.history_service import ProductHistoryService
from apps.products.models import Product, ProductHistoryActionType
from apps.products.policies import DeletionPolicy
from apps.products.types import ProductTypeRegistry


# Per-subtype knowledge (model, related_name, allowed/required/enum fields) moved
# to apps.products.types (ProductTypeStrategy + ProductTypeRegistry). Adding a
# media type no longer touches this module — see the Design Patterns report.
PRODUCT_FIELDS = {
    "product_type",
    "title",
    "category",
    "general_description",
    "height",
    "width",
    "length",
    "weight",
    "barcode",
    "image_url",
    "original_value",
    "current_price",
    "stock_quantity",
    "status",
}


# Design note (refactored): ProductService is now a thin CUD orchestration
# boundary. Subtype rules live in ProductTypeStrategy/ProductTypeRegistry, the
# delete caps + delete-vs-deactivate rule live in DeletionPolicy, and audit lives
# in ProductHistoryService. This resolves the earlier SRP/OCP/DIP/ISP tensions of
# one fat static class. See the Design Patterns report.
class ProductService:
    """
    Product manager write boundary for CUD use cases.
    This service enforces the design rules that must not be bypassed by the frontend: 
    price range, stock-aware delete behavior, per-request delete cap, daily delete cap, and stock adjustment reasons.
    """

    # Kept as aliases (external callers/tests may reference them); the source of
    # truth for the caps is DeletionPolicy.
    MAX_DELETE_PER_REQUEST = DeletionPolicy.MAX_PER_REQUEST
    MAX_DELETE_PER_DAY = DeletionPolicy.MAX_PER_DAY

    @staticmethod
    @transaction.atomic
    def create_product(*, data: dict, manager_id: str = "manager") -> Product:
        type_details = data.pop("type_details", {})
        product = Product(**{key: value for key, value in data.items() if key in PRODUCT_FIELDS})
        product.full_clean()
        strategy = ProductTypeRegistry.get(product.product_type)
        ProductService._raise_if_missing(strategy.validate_required(type_details, require_all=True))
        product.save()
        strategy.sync(product=product, details=type_details)
        ProductHistoryService.log(
            product=product,
            action_type=ProductHistoryActionType.CREATE,
            performed_by=manager_id,
            changes={"after": ProductService.snapshot(product)},
        )
        return product

    @staticmethod
    @transaction.atomic
    def update_product(*, product: Product, data: dict, manager_id: str = "manager") -> Product:
        type_details = data.pop("type_details", None)
        stock_reason = data.pop("stock_adjustment_reason", "")
        before = ProductService.snapshot(product)
        stock_changed = "stock_quantity" in data and data["stock_quantity"] != product.stock_quantity

        if stock_changed and not stock_reason:
            raise ValidationError({"stock_adjustment_reason": "Stock adjustment reason is required."})

        previous_type = product.product_type
        for field_name, value in data.items():
            if field_name in PRODUCT_FIELDS:
                setattr(product, field_name, value)

        product.full_clean()
        product.save()

        type_changed = product.product_type != previous_type
        if type_changed:
            ProductTypeRegistry.delete_other_details(product=product, keep_type=product.product_type)

        if type_details is not None:
            # Type changed -> a fresh subtype row needs all required fields; same
            # type -> partial edit, only reject required fields explicitly blanked.
            strategy = ProductTypeRegistry.get(product.product_type)
            ProductService._raise_if_missing(
                strategy.validate_required(type_details, require_all=type_changed)
            )
            strategy.sync(product=product, details=type_details)

        action_type = ProductHistoryActionType.STOCK_ADJUST if stock_changed else ProductHistoryActionType.UPDATE
        ProductHistoryService.log(
            product=product,
            action_type=action_type,
            performed_by=manager_id,
            reason=stock_reason,
            changes={"before": before, "after": ProductService.snapshot(product)},
        )
        return product

    # /*
    #  * SOLID Review
    #  * Principle: SRP
    #  * Reason: delete_products mixes three policy concerns — the per-request cap, the per-manager
    #  *   daily cap (a ProductHistory COUNT query), and the per-product delete-vs-deactivate
    #  *   decision — with the persistence/audit loop.
    #  * Impact: Changing any policy (e.g. configurable or per-role caps, "deactivate when the
    #  *   product has open orders") means editing this method and risks the unrelated create/update
    #  *   paths; the rules cannot be unit-tested without driving the whole delete flow + DB.
    #  * Improvement: Extract a DeletionPolicy collaborator (check_request_size, check_daily_cap,
    #  *   resolve_status) so delete_products becomes pure orchestration and each rule is tested alone.
    #  */
    @staticmethod
    @transaction.atomic
    def delete_products(*, product_ids: list[str], manager_id: str = "manager") -> list[Product]:
        policy = DeletionPolicy()
        policy.check_request_size(len(product_ids))
        policy.check_daily_cap(manager_id=manager_id, adding=len(product_ids))

        products = list(Product.objects.filter(product_id__in=product_ids).order_by("title"))
        if len(products) != len(set(product_ids)):
            raise ValidationError({"product_ids": "One or more products do not exist."})

        changed_products: list[Product] = []
        for product in products:
            before = ProductService.snapshot(product)
            product.status, action_type = policy.resolve_status(product)
            product.full_clean()
            product.save(update_fields=["status", "updated_at"])
            ProductHistoryService.log(
                product=product,
                action_type=action_type,
                performed_by=manager_id,
                changes={"before": before, "after": ProductService.snapshot(product)},
            )
            changed_products.append(product)

        return changed_products

    @staticmethod
    def snapshot(product: Product) -> dict:
        return {
            "product_id": str(product.product_id),
            "product_type": product.product_type,
            "title": product.title,
            "category": product.category,
            "barcode": product.barcode,
            "current_price": product.current_price,
            "original_value": product.original_value,
            "stock_quantity": product.stock_quantity,
            "status": product.status,
        }

    @staticmethod
    def _raise_if_missing(missing: list[str]) -> None:
        """Raise the required-type-details error in the exact shape the API and
        tests expect. Strategies return the missing-field list; the service owns
        the Django error contract so strategies stay framework-agnostic."""
        if missing:
            # Django ValidationError does not support nested dicts, so surface the
            # required fields as a flat list of messages under "type_details".
            raise ValidationError(
                {"type_details": [f"{field} is required for this product type." for field in missing]}
            )
