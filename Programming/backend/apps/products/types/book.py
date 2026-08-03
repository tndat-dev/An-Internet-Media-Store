from apps.products.models import Book, ProductType
from apps.products.types.base import ProductTypeStrategy
from apps.products.types.registry import ProductTypeRegistry


class BookTypeStrategy(ProductTypeStrategy):
    product_type = ProductType.BOOK
    model = Book
    related_name = "book_details"
    allowed_fields = frozenset(
        {"authors", "cover_type", "publisher", "publication_date", "pages", "language", "genre"}
    )
    required_fields = ("authors", "cover_type", "publisher", "publication_date")
    enum_fields = {"cover_type": ["Paperback", "Hardcover"]}


ProductTypeRegistry.register(BookTypeStrategy())
