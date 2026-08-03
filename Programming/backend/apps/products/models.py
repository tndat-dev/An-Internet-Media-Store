import uuid
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q

from apps.products.validators import (
    PRICE_RATIO_MAX,
    PRICE_RATIO_MIN,
    validate_product_price,
)


class ProductType(models.TextChoices):
    BOOK = "BOOK", "Book"
    CD = "CD", "CD"
    DVD = "DVD", "DVD"
    NEWSPAPER = "NEWSPAPER", "Newspaper"


class ProductStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    DEACTIVATED = "DEACTIVATED", "Deactivated"
    DELETED = "DELETED", "Deleted"


class ProductHistoryActionType(models.TextChoices):
    CREATE = "CREATE", "Create"
    UPDATE = "UPDATE", "Update"
    DELETE = "DELETE", "Delete"
    DEACTIVATE = "DEACTIVATE", "Deactivate"
    STOCK_ADJUST = "STOCK_ADJUST", "Stock adjust"


class Product(models.Model):
    """
    Cohesion boundary for shared product data.
    Type-specific media attributes live in 1-to-1 extension models so 
    CUD services can validate common rules once without mixing Book/CD/DVD fields into every product operation.
    """

    product_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product_type = models.CharField(max_length=20, choices=ProductType.choices)
    title = models.CharField(max_length=255)
    category = models.CharField(max_length=100)
    general_description = models.TextField(blank=True)
    height = models.DecimalField(max_digits=10, decimal_places=2)
    width = models.DecimalField(max_digits=10, decimal_places=2)
    length = models.DecimalField(max_digits=10, decimal_places=2)
    weight = models.DecimalField(max_digits=10, decimal_places=2)
    barcode = models.CharField(max_length=64, unique=True)
    image_url = models.URLField(max_length=500, blank=True)
    original_value = models.DecimalField(max_digits=14, decimal_places=2)
    current_price = models.DecimalField(max_digits=14, decimal_places=2)
    stock_quantity = models.PositiveIntegerField(default=0)
    status = models.CharField(
        max_length=20,
        choices=ProductStatus.choices,
        default=ProductStatus.ACTIVE,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["title"]
        constraints = [
            models.CheckConstraint(
                name="ck_products_dimensions_non_negative",
                condition=Q(height__gte=0) & Q(width__gte=0) & Q(length__gte=0) & Q(weight__gte=0),
            ),
            models.CheckConstraint(
                name="ck_products_values_non_negative",
                condition=Q(original_value__gte=0) & Q(current_price__gte=0),
            ),
            models.CheckConstraint(
                name="ck_products_price_lower_bound",
                condition=Q(current_price__gte=F("original_value") * PRICE_RATIO_MIN),
            ),
            models.CheckConstraint(
                name="ck_products_price_upper_bound",
                condition=Q(current_price__lte=F("original_value") * PRICE_RATIO_MAX),
            ),
            models.CheckConstraint(
                name="ck_products_deleted_only_when_stock_zero",
                condition=~Q(status=ProductStatus.DELETED) | Q(stock_quantity=0),
            ),
        ]

    def __str__(self) -> str:
        return f"{self.title} ({self.product_type})"

    def clean(self) -> None:
        errors: dict[str, str] = {}

        if not validate_product_price(self.original_value, self.current_price):
            errors["current_price"] = "Current price must be from 30% to 150% of original value."

        numeric_fields = ["height", "width", "length", "weight", "original_value", "current_price"]
        for field_name in numeric_fields:
            value = getattr(self, field_name)
            if value is not None and Decimal(value) < 0:
                errors[field_name] = "Value must be non-negative."

        if self.status == ProductStatus.DELETED and self.stock_quantity != 0:
            errors["stock_quantity"] = "Only products with zero stock can be marked as deleted."

        if errors:
            raise ValidationError(errors)


class Book(models.Model):
    product = models.OneToOneField(Product, on_delete=models.CASCADE, related_name="book_details")
    authors = models.CharField(max_length=255)
    cover_type = models.CharField(max_length=100, blank=True)
    publisher = models.CharField(max_length=255, blank=True)
    publication_date = models.DateField(null=True, blank=True)
    pages = models.PositiveIntegerField(null=True, blank=True)
    language = models.CharField(max_length=80, blank=True)
    genre = models.CharField(max_length=100, blank=True)


class CD(models.Model):
    product = models.OneToOneField(Product, on_delete=models.CASCADE, related_name="cd_details")
    artists = models.CharField(max_length=255)
    record_label = models.CharField(max_length=255, blank=True)
    tracklist = models.TextField(blank=True)
    genre = models.CharField(max_length=100, blank=True)
    release_date = models.DateField(null=True, blank=True)


class DVD(models.Model):
    product = models.OneToOneField(Product, on_delete=models.CASCADE, related_name="dvd_details")
    disc_type = models.CharField(max_length=80, blank=True)
    director = models.CharField(max_length=255, blank=True)
    runtime_minutes = models.PositiveIntegerField(null=True, blank=True)
    studio = models.CharField(max_length=255, blank=True)
    language = models.CharField(max_length=80, blank=True)
    subtitles = models.CharField(max_length=255, blank=True)
    release_date = models.DateField(null=True, blank=True)
    genre = models.CharField(max_length=100, blank=True)


class Newspaper(models.Model):
    product = models.OneToOneField(Product, on_delete=models.CASCADE, related_name="newspaper_details")
    publisher = models.CharField(max_length=255, blank=True)
    publication_date = models.DateField(null=True, blank=True)
    issue_number = models.CharField(max_length=80, blank=True)
    # Restored from the approved data model (DetailedDesign/DataModeling/aimsdb.sql).
    editor_in_chief = models.CharField(max_length=255, blank=True)
    publication_frequency = models.CharField(max_length=100, blank=True)
    issn = models.CharField(max_length=100, blank=True)
    language = models.CharField(max_length=80, blank=True)
    sections = models.TextField(blank=True)


class ProductHistory(models.Model):
    """
    Audit trail for Product Manager actions.
    The project has not added the Users app yet, so performed_by intentionally
    stores a stable manager identifier string until the auth boundary exists.
    """

    history_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="histories")
    action_type = models.CharField(max_length=20, choices=ProductHistoryActionType.choices)
    performed_by = models.ForeignKey(
        "users.User",
        on_delete=models.PROTECT,
        related_name="product_histories",
        null=True,
        blank=True,
        help_text="Manager/admin who performed the action. Always set by ProductHistoryService.",
    )
    reason = models.CharField(max_length=255, blank=True)
    changes = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
