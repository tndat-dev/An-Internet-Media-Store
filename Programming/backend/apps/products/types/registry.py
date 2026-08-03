"""Registry mapping ``ProductType`` -> ``ProductTypeStrategy``.

This is the Open/Closed seam: create / update / delete / serialize / prefetch all
dispatch through the registry, so a new media type is added by registering one
strategy rather than editing those call sites.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError

from apps.products.types.base import ProductTypeStrategy


class ProductTypeRegistry:
    _strategies: dict[str, ProductTypeStrategy] = {}

    @classmethod
    def register(cls, strategy: ProductTypeStrategy) -> None:
        cls._strategies[strategy.product_type] = strategy

    @classmethod
    def get(cls, product_type: str) -> ProductTypeStrategy:
        try:
            return cls._strategies[product_type]
        except KeyError as exc:  # unknown type -> a validation error, never a 500
            raise ValidationError(
                {"product_type": f"Unsupported product type: {product_type}."}
            ) from exc

    @classmethod
    def all(cls) -> list[ProductTypeStrategy]:
        return list(cls._strategies.values())

    @classmethod
    def related_names(cls) -> list[str]:
        """Reverse accessors for select_related() — keeps the prefetch in sync
        with the registered subtypes automatically."""
        return [strategy.related_name for strategy in cls._strategies.values()]

    @classmethod
    def delete_other_details(cls, *, product, keep_type: str) -> None:
        """Delete subtype rows for every type except ``keep_type`` (used when a
        product's type changes during an update)."""
        for strategy in cls._strategies.values():
            if strategy.product_type == keep_type:
                continue
            if hasattr(product, strategy.related_name):
                getattr(product, strategy.related_name).delete()
