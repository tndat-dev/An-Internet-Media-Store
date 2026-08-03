from apps.products.models import CD, ProductType
from apps.products.types.base import ProductTypeStrategy
from apps.products.types.registry import ProductTypeRegistry


class CDTypeStrategy(ProductTypeStrategy):
    product_type = ProductType.CD
    model = CD
    related_name = "cd_details"
    allowed_fields = frozenset({"artists", "record_label", "tracklist", "genre", "release_date"})
    required_fields = ("artists", "record_label", "tracklist", "genre")
    enum_fields = {}


ProductTypeRegistry.register(CDTypeStrategy())
