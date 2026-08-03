from decimal import Decimal

from rest_framework import serializers

from apps.carts.models import Cart, CartItem
from apps.carts.services import CartService, validate_product_available


class CartItemSerializer(serializers.ModelSerializer):
    cartItemId = serializers.UUIDField(source="cart_item_id", read_only=True)
    productId = serializers.UUIDField(source="product.product_id", read_only=True)
    productTitle = serializers.CharField(source="product.title", read_only=True)
    productType = serializers.CharField(source="product.product_type", read_only=True)
    imageUrl = serializers.CharField(source="product.image_url", read_only=True)
    unitPrice = serializers.DecimalField(source="product.current_price", max_digits=12, decimal_places=2, read_only=True)
    lineSubtotal = serializers.SerializerMethodField()
    stockQuantity = serializers.IntegerField(source="product.stock_quantity", read_only=True)
    productStatus = serializers.CharField(source="product.status", read_only=True)
    stockWarning = serializers.SerializerMethodField()

    class Meta:
        model = CartItem
        fields = [
            "cartItemId",
            "productId",
            "productTitle",
            "productType",
            "imageUrl",
            "unitPrice",
            "quantity",
            "lineSubtotal",
            "stockQuantity",
            "productStatus",
            "stockWarning",
        ]

    def get_lineSubtotal(self, item: CartItem) -> str:
        return f"{Decimal(item.product.current_price * item.quantity):.2f}"

    def get_stockWarning(self, item: CartItem) -> dict | None:
        result = validate_product_available(item.product, item.quantity)
        if result["valid"]:
            return None
        return {
            "reason": result["reason"],
            "availableQuantity": item.product.stock_quantity,
            "missingQuantity": result["missing_quantity"],
        }


# /*
#  * SOLID Review
#  * Principle: SRP/DIP
#  * Reason: CartSerializer formats response data but also calls CartService to recalculate checkout validation and totals.
#  * Impact: Serialization becomes coupled to business service behavior, making API output tests depend on cart validation internals.
#  * Improvement: Pass precomputed cart summary/checkability data from a service DTO or expose dedicated read-model methods.
#  */
class CartSerializer(serializers.ModelSerializer):
    cartId = serializers.UUIDField(source="cart_id", read_only=True)
    cartToken = serializers.CharField(source="cart_token", read_only=True)
    subtotalExclVat = serializers.SerializerMethodField()
    totalItems = serializers.SerializerMethodField()
    canPlaceOrder = serializers.SerializerMethodField()
    stockErrors = serializers.SerializerMethodField()
    items = CartItemSerializer(many=True, read_only=True)

    class Meta:
        model = Cart
        fields = [
            "cartId",
            "cartToken",
            "status",
            "items",
            "subtotalExclVat",
            "totalItems",
            "canPlaceOrder",
            "stockErrors",
        ]

    def get_subtotalExclVat(self, cart: Cart) -> str:
        return f"{CartService.subtotal_excl_vat(cart):.2f}"

    def get_totalItems(self, cart: Cart) -> int:
        return sum(item.quantity for item in cart.items.all())

    def get_canPlaceOrder(self, cart: Cart) -> bool:
        return len(CartService.validate_cart_for_checkout(cart)) == 0

    def get_stockErrors(self, cart: Cart) -> list[dict]:
        return CartService.validate_cart_for_checkout(cart)


class CartItemCreateSerializer(serializers.Serializer):
    productId = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1)


class CartItemUpdateSerializer(serializers.Serializer):
    quantity = serializers.IntegerField(min_value=1)
