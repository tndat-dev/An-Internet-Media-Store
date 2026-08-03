from rest_framework import serializers

from apps.products.models import (
    Product,
    ProductHistory,
    ProductStatus,
    ProductType,
)
from apps.products.types import ProductTypeRegistry
from apps.products.validators import validate_product_price


class ProductWriteSerializer(serializers.Serializer):
    """
    Coupling/Cohesion level:
    - Coupling: Data coupling with ProductType/ProductStatus enums and validate_product_price.
    - Cohesion: Communicational cohesion.

    Reason why: The class validates one manager create-product payload while mutation behavior stays in ProductService.
    """

    product_type = serializers.ChoiceField(choices=ProductType.choices)
    title = serializers.CharField(max_length=255)
    category = serializers.CharField(max_length=100)
    general_description = serializers.CharField(required=False, allow_blank=True)
    height = serializers.DecimalField(max_digits=10, decimal_places=2)
    width = serializers.DecimalField(max_digits=10, decimal_places=2)
    length = serializers.DecimalField(max_digits=10, decimal_places=2)
    weight = serializers.DecimalField(max_digits=10, decimal_places=2)
    barcode = serializers.CharField(max_length=64)
    image_url = serializers.URLField(max_length=500, required=False, allow_blank=True)
    original_value = serializers.DecimalField(max_digits=14, decimal_places=2)
    current_price = serializers.DecimalField(max_digits=14, decimal_places=2)
    stock_quantity = serializers.IntegerField(min_value=0)
    status = serializers.ChoiceField(choices=ProductStatus.choices, required=False)
    type_details = serializers.DictField(required=False)
    stock_adjustment_reason = serializers.CharField(required=False, allow_blank=True, write_only=True)

    def validate(self, attrs):
        if not validate_product_price(attrs.get("original_value"), attrs.get("current_price")):
            raise serializers.ValidationError(
                {"current_price": "Current price must be from 30% to 150% of original value."}
            )
        return attrs


class ProductPatchSerializer(ProductWriteSerializer):
    """
    Coupling/Cohesion level:
    - Coupling: Stamp coupling with ProductWriteSerializer and optional Product instance state.
    - Cohesion: Communicational cohesion.

    Reason why: The class specializes the product write schema for partial manager updates.
    """

    product_type = serializers.ChoiceField(choices=ProductType.choices, required=False)
    title = serializers.CharField(max_length=255, required=False)
    category = serializers.CharField(max_length=100, required=False)
    height = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    width = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    length = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    weight = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    barcode = serializers.CharField(max_length=64, required=False)
    original_value = serializers.DecimalField(max_digits=14, decimal_places=2, required=False)
    current_price = serializers.DecimalField(max_digits=14, decimal_places=2, required=False)
    stock_quantity = serializers.IntegerField(min_value=0, required=False)

    def validate(self, attrs):
        original_value = attrs.get("original_value", getattr(self.instance, "original_value", None))
        current_price = attrs.get("current_price", getattr(self.instance, "current_price", None))
        if not validate_product_price(original_value, current_price):
            raise serializers.ValidationError(
                {"current_price": "Current price must be from 30% to 150% of original value."}
            )
        return attrs


class ProductSerializer(serializers.ModelSerializer):
    """
    Coupling/Cohesion level:
    - Coupling: Stamp coupling with Product objects; control coupling through product_type-specific detail extraction.
    - Cohesion: Communicational cohesion.

    Reason why: The class serializes the manager product aggregate with fields needed by the CUD workspace.
    """

    type_details = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "product_id",
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
            "type_details",
            "created_at",
            "updated_at",
        ]

    def get_type_details(self, product: Product) -> dict:
        return serialize_type_details(product)


class CustomerProductSerializer(serializers.ModelSerializer):
    """
    Coupling/Cohesion level:
    - Coupling: Stamp coupling with Product objects; data coupling with customer product cards/detail popup through public DTO fields.
    - Cohesion: Communicational cohesion.

    Reason why: The class exposes only customer-visible product information and keeps manager-only fields out of the read API.
    """

    description = serializers.CharField(source="general_description")
    price = serializers.DecimalField(source="current_price", max_digits=12, decimal_places=2)
    is_available = serializers.SerializerMethodField()
    type_details = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "product_id",
            "product_type",
            "title",
            "category",
            "description",
            "image_url",
            "price",
            "stock_quantity",
            "status",
            "is_available",
            "height",
            "width",
            "length",
            "weight",
            "barcode",
            "type_details",
        ]

    def get_is_available(self, product: Product) -> bool:
        return product.status == ProductStatus.ACTIVE

    def get_type_details(self, product: Product) -> dict:
        return serialize_type_details(product)


# Subtype serialization is delegated to the per-type strategy via the registry
# (Strategy + Registry pattern), so adding a media type needs no change here.
# This resolves the previous OCP violation (a hard-coded product_type -> related
# name map duplicated from services/selectors). See Design Patterns report.
def serialize_type_details(product: Product) -> dict:
    return ProductTypeRegistry.get(product.product_type).serialize(product)


class ProductDeleteSerializer(serializers.Serializer):
    """
    Coupling/Cohesion level:
    - Coupling: Data coupling with ProductDeleteView through product_ids only.
    - Cohesion: Functional cohesion.

    Reason why: The class only validates the delete request input and request-size limit.
    """

    product_ids = serializers.ListField(
        child=serializers.UUIDField(),
        allow_empty=False,
        max_length=10,
    )


class ProductHistorySerializer(serializers.ModelSerializer):
    """
    Coupling/Cohesion level:
    - Coupling: Stamp coupling with ProductHistory and related Product title/id.
    - Cohesion: Communicational cohesion.

    Reason why: The class serializes audit records that describe product management actions.
    """

    product_id = serializers.UUIDField(source="product.product_id", read_only=True)
    product_title = serializers.CharField(source="product.title", read_only=True)
    performed_by = serializers.SerializerMethodField()

    class Meta:
        model = ProductHistory
        fields = [
            "history_id",
            "product_id",
            "product_title",
            "action_type",
            "performed_by",
            "reason",
            "changes",
            "created_at",
        ]

    def get_performed_by(self, obj) -> str | None:
        return obj.performed_by.username if obj.performed_by_id else None
