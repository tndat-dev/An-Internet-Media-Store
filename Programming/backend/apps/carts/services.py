from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Prefetch

from apps.carts.models import Cart, CartItem
from apps.products.models import Product, ProductStatus


def validate_cart_item_quantity(requested_quantity: int, stock_quantity: int) -> dict:
    if requested_quantity <= 0:
        return {
            "valid": False,
            "reason": "INVALID_QUANTITY",
            "missing_quantity": 0,
        }

    if stock_quantity < 0:
        return {
            "valid": False,
            "reason": "INVALID_STOCK",
            "missing_quantity": 0,
        }

    if requested_quantity > stock_quantity:
        return {
            "valid": False,
            "reason": "INSUFFICIENT_STOCK",
            "missing_quantity": requested_quantity - stock_quantity,
        }

    return {
        "valid": True,
        "reason": None,
        "missing_quantity": 0,
    }


def validate_product_available(product: Product, requested_quantity: int) -> dict:
    if product.status != ProductStatus.ACTIVE:
        return {
            "valid": False,
            "reason": "PRODUCT_UNAVAILABLE",
            "missing_quantity": 0,
        }
    return validate_cart_item_quantity(requested_quantity, product.stock_quantity)


# /*
#  * SOLID Review
#  * Principle: SRP/DIP
#  * Reason: CartService combines cart retrieval/mutation, stock validation coordination, subtotal/weight calculations, and direct Product/CartItem ORM access.
#  * Impact: Cart behavior is harder to test without database models, and checkout/cart changes can force edits in the same service.
#  * Improvement: Keep cart commands here but extract stock policy, cart totals, and repository access behind focused collaborators.
#  */
class CartService:
    """
    Coupling/Cohesion: keeps cart mutation and stock validation together while
    delegating product availability to Product fields and leaving order creation
    to apps.orders services.
    """

    @staticmethod
    def get_or_create_cart(cart_token: str) -> Cart:
        if not cart_token or not cart_token.strip():
            raise ValidationError({"cartToken": "Cart token is required."})

        cart, _ = Cart.objects.get_or_create(cart_token=cart_token.strip())
        return cart

    @staticmethod
    def get_cart(cart_token: str) -> Cart:
        CartService.get_or_create_cart(cart_token)
        return Cart.objects.prefetch_related(
            Prefetch(
                "items",
                queryset=CartItem.objects.select_related("product"),
            )
        ).get(cart_token=cart_token.strip())

    @staticmethod
    def subtotal_excl_vat(cart: Cart) -> Decimal:
        subtotal = Decimal("0.00")
        for item in cart.items.all():
            subtotal += item.product.current_price * item.quantity
        return subtotal

    @staticmethod
    def total_weight_kg(cart: Cart) -> Decimal:
        total_weight = Decimal("0.00")
        for item in cart.items.all():
            total_weight += item.product.weight * item.quantity
        return total_weight

    @staticmethod
    def validate_cart_for_checkout(cart: Cart) -> list[dict]:
        errors = []
        if not cart.items.exists():
            errors.append({"reason": "EMPTY_CART"})
            return errors

        for item in cart.items.select_related("product"):
            result = validate_product_available(item.product, item.quantity)
            if not result["valid"]:
                errors.append(
                    {
                        "cartItemId": str(item.cart_item_id),
                        "productId": str(item.product.product_id),
                        "productTitle": item.product.title,
                        "requestedQuantity": item.quantity,
                        "availableQuantity": item.product.stock_quantity,
                        "reason": result["reason"],
                        "missingQuantity": result["missing_quantity"],
                    }
                )
        return errors

    @staticmethod
    @transaction.atomic
    def add_item(cart_token: str, product_id: str, quantity: int) -> Cart:
        cart = CartService.get_or_create_cart(cart_token)
        product = Product.objects.get(product_id=product_id)
        existing_item = CartItem.objects.filter(cart=cart, product=product).first()
        requested_quantity = quantity + (existing_item.quantity if existing_item else 0)

        if quantity <= 0:
            raise ValidationError({"quantity": "INVALID_QUANTITY"})
        if product.status != ProductStatus.ACTIVE:
            raise ValidationError({"quantity": "PRODUCT_UNAVAILABLE"})

        if existing_item:
            existing_item.quantity = requested_quantity
            existing_item.save(update_fields=["quantity", "updated_at"])
        else:
            CartItem.objects.create(cart=cart, product=product, quantity=quantity)

        return CartService.get_cart(cart_token)

    @staticmethod
    @transaction.atomic
    def update_item(cart_token: str, cart_item_id: str, quantity: int) -> Cart:
        cart = CartService.get_or_create_cart(cart_token)
        item = CartItem.objects.select_related("product").get(cart=cart, cart_item_id=cart_item_id)

        if quantity <= 0:
            raise ValidationError({"quantity": "INVALID_QUANTITY"})
        if item.product.status != ProductStatus.ACTIVE:
            raise ValidationError({"quantity": "PRODUCT_UNAVAILABLE"})

        item.quantity = quantity
        item.save(update_fields=["quantity", "updated_at"])
        return CartService.get_cart(cart_token)

    @staticmethod
    @transaction.atomic
    def remove_item(cart_token: str, cart_item_id: str) -> Cart:
        cart = CartService.get_or_create_cart(cart_token)
        CartItem.objects.get(cart=cart, cart_item_id=cart_item_id).delete()
        return CartService.get_cart(cart_token)

    @staticmethod
    @transaction.atomic
    def clear(cart: Cart) -> None:
        """Empty a cart's items once its order has been fulfilled (paid).

        Called by order fulfillment, not by checkout confirmation: confirm_order
        only marks the cart CHECKED_OUT and still needs the items for re-validation
        in the confirm->pay window.
        """
        cart.items.all().delete()
