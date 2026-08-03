import uuid

from django.db import models

from apps.products.models import Product


class CartStatus(models.TextChoices):
    """Coupling/Cohesion: groups cart lifecycle states in one shared enum.
    It is lowly coupled to models that use cart status while keeping status
    semantics cohesive for cart and checkout logic.
    """
    OPEN = "OPEN", "Open"
    CHECKED_OUT = "CHECKED_OUT", "Checked out"


class Cart(models.Model):
    cart_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cart_token = models.CharField(max_length=64, unique=True)
    status = models.CharField(
        max_length=20,
        choices=CartStatus.choices,
        default=CartStatus.OPEN,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return f"Cart {self.cart_token}"


class CartItem(models.Model):
    """Coupling/Cohesion: owns individual cart item data and product relation.
    It is cohesively focused on item quantity/product reference and minimally
    coupled to Cart, Product, and checkout stock validation.
    """
    cart_item_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="cart_items")
    quantity = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(fields=["cart", "product"], name="uq_cart_items_cart_product"),
        ]

    def __str__(self) -> str:
        return f"{self.product.title} x {self.quantity}"
