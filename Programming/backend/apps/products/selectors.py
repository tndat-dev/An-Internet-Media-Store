from decimal import Decimal, InvalidOperation

from django.db.models import QuerySet

from apps.products.models import Product, ProductStatus
from apps.products.types import ProductTypeRegistry

# Customer-facing sort options (OCP registry): add a new sort by adding an entry
# here — no edit to the query method. DEFAULT_SORT is used for unknown/empty input.
DEFAULT_SORT = "title"
CUSTOMER_SORTS = {
    "title": "title",
    "newest": "-created_at",
    "price_asc": "current_price",
    "price_desc": "-current_price",
}


# /*
#  * SOLID Review
#  * Principle: OCP (+DRY)
#  * Reason: The select_related list hard-codes every subtype's reverse accessor, duplicating the
#  *   subtype knowledge already encoded in services.TYPE_DETAIL_CONFIG and serialize_type_details.
#  * Impact: Adding a media type requires editing this literal too; forgetting it silently
#  *   reintroduces an N+1 query for the new type's detail rows.
#  * Improvement: Build the prefetch from ProductTypeRegistry.related_names() so it extends
#  *   automatically when a new subtype strategy is registered.
#  */
def _with_type_details() -> QuerySet[Product]:
    # Prefetch each subtype's detail row. The accessor list comes from the registry
    # so a newly registered product type is included automatically (no literal here).
    return Product.objects.all().select_related(*ProductTypeRegistry.related_names())


class ProductSelector:
    """
    Coupling/Cohesion level:
    - Coupling: Data coupling with product views through explicit query parameters; stamp coupling through Product querysets.
    - Cohesion: Functional cohesion.

    Reason why: The class keeps read/query behavior in one boundary so API views stay thin and manager/customer reads can evolve separately.
    """

    @staticmethod
    def list_for_manager(*, include_deleted: bool = False, search: str = "") -> QuerySet[Product]:
        queryset = _with_type_details()

        if not include_deleted:
            queryset = queryset.exclude(status=ProductStatus.DELETED)

        if search:
            queryset = queryset.filter(title__icontains=search)

        return queryset.order_by("title")

    @staticmethod
    def get_for_manager(product_id: str) -> Product:
        return ProductSelector.list_for_manager(include_deleted=True).get(product_id=product_id)

    @staticmethod
    # Design note (refactored): sort options live in the module-level CUSTOMER_SORTS
    # registry (OCP) — adding a sort no longer edits this method body.
    def list_for_customer(
        *,
        search: str = "",
        category: str = "",
        min_price: str = "",
        max_price: str = "",
        sort: str = "",
    ) -> QuerySet[Product]:
        """
        Coupling/Cohesion level:
        - Coupling: Data coupling with customer list API through primitive filter values.
        - Cohesion: Functional cohesion.

        Reason why: The method only builds the customer-visible product listing query
        and excludes deleted products. The view applies page-based pagination so the
        customer can move beyond the first 20 products.
        """

        queryset = _with_type_details().exclude(status=ProductStatus.DELETED)

        if search:
            queryset = queryset.filter(title__icontains=search)

        if category:
            queryset = queryset.filter(category__iexact=category)

        parsed_min_price = ProductSelector._parse_price(min_price)
        if parsed_min_price is not None:
            queryset = queryset.filter(current_price__gte=parsed_min_price)

        parsed_max_price = ProductSelector._parse_price(max_price)
        if parsed_max_price is not None:
            queryset = queryset.filter(current_price__lte=parsed_max_price)

        return queryset.order_by(CUSTOMER_SORTS.get(sort, CUSTOMER_SORTS[DEFAULT_SORT]))

    @staticmethod
    def get_for_customer(product_id: str) -> Product:
        """
        Coupling/Cohesion level:
        - Coupling: Data coupling with customer detail API through product_id.
        - Cohesion: Functional cohesion.

        Reason why: The method returns one customer-visible product aggregate and hides deleted products.
        """

        return _with_type_details().exclude(status=ProductStatus.DELETED).get(product_id=product_id)

    @staticmethod
    def _parse_price(value: str) -> Decimal | None:
        if not value:
            return None
        try:
            return Decimal(value)
        except (InvalidOperation, TypeError):
            return None
