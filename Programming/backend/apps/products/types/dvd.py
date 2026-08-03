from apps.products.models import DVD, ProductType
from apps.products.types.base import ProductTypeStrategy
from apps.products.types.registry import ProductTypeRegistry


class DVDTypeStrategy(ProductTypeStrategy):
    product_type = ProductType.DVD
    model = DVD
    related_name = "dvd_details"
    allowed_fields = frozenset(
        {"disc_type", "director", "runtime_minutes", "studio", "language", "subtitles", "release_date", "genre"}
    )
    required_fields = ("disc_type", "director", "runtime_minutes", "studio", "language", "subtitles")
    enum_fields = {"disc_type": ["Blu-ray", "HD-DVD"]}


ProductTypeRegistry.register(DVDTypeStrategy())
