from apps.products.models import Newspaper, ProductType
from apps.products.types.base import ProductTypeStrategy
from apps.products.types.registry import ProductTypeRegistry


class NewspaperTypeStrategy(ProductTypeStrategy):
    product_type = ProductType.NEWSPAPER
    model = Newspaper
    related_name = "newspaper_details"
    allowed_fields = frozenset(
        {"publisher", "publication_date", "issue_number", "editor_in_chief", "publication_frequency", "issn", "language", "sections"}
    )
    required_fields = ("editor_in_chief", "publisher", "publication_date")
    enum_fields = {}


ProductTypeRegistry.register(NewspaperTypeStrategy())
