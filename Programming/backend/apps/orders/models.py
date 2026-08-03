import uuid

from django.db import models
from django.db.models import F, Q

from apps.carts.models import Cart
from apps.products.models import Product


class OrderStatus(models.TextChoices):
    """Coupling/Cohesion: centralizes order workflow states in one enum.
    It stays low-coupled and reusable across order services, validators,
    and payment logic.
    """
    PENDING_PAYMENT = "PENDING_PAYMENT", "Pending payment"
    PENDING_PROCESSING = "PENDING_PROCESSING", "Pending processing"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Rejected"
    CANCELLED = "CANCELLED", "Cancelled"


class Order(models.Model):
    order_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cart = models.ForeignKey(Cart, on_delete=models.SET_NULL, null=True, blank=True, related_name="orders")
    status = models.CharField(
        max_length=24,
        choices=OrderStatus.choices,
        default=OrderStatus.PENDING_PAYMENT,
    )
    total_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    order_view_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    cancel_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    processed_by = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        related_name="processed_orders",
        null=True,
        blank=True,
        help_text="Manager who approved/rejected the order (set during order processing).",
    )
    processed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Order {self.order_id}"


class OrderItem(models.Model):
    """Coupling/Cohesion: captures product snapshot for the order.
    It is cohesive around order line details and only couples to Order and
    Product read data.
    """
    order_item_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="order_items")
    product_title = models.CharField(max_length=255)
    unit_price = models.DecimalField(max_digits=14, decimal_places=2)
    quantity = models.PositiveIntegerField()
    line_amount_excl_vat = models.DecimalField(max_digits=14, decimal_places=2)
    line_amount_incl_vat = models.DecimalField(max_digits=14, decimal_places=2)

    class Meta:
        ordering = ["product_title"]
        constraints = [
            models.UniqueConstraint(fields=["order", "product"], name="uq_order_items_order_product"),
            models.CheckConstraint(
                name="ck_order_items_unit_price_non_negative",
                condition=Q(unit_price__gte=0),
            ),
            models.CheckConstraint(
                name="ck_order_items_quantity_positive",
                condition=Q(quantity__gt=0),
            ),
            models.CheckConstraint(
                name="ck_order_items_line_amounts_non_negative",
                condition=Q(line_amount_excl_vat__gte=0) & Q(line_amount_incl_vat__gte=0),
            ),
        ]


class DeliveryInfo(models.Model):
    """Coupling/Cohesion: holds delivery details for a specific order.
    It keeps customer/address data cohesive while coupling only to Order and
    delivery fee calculation.
    """
    delivery_info_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name="delivery_info")
    customer_name = models.CharField(max_length=255)
    phone_number = models.CharField(max_length=30)
    email = models.EmailField()
    delivery_province = models.CharField(max_length=100)
    delivery_address = models.TextField()
    delivery_method = models.CharField(max_length=40, default="STANDARD")
    delivery_instructions = models.TextField(blank=True)
    expected_date = models.DateField(null=True, blank=True)
    shipping_fee = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    class Meta:
        constraints = [
            models.CheckConstraint(
                name="ck_delivery_infos_shipping_fee_non_negative",
                condition=Q(shipping_fee__gte=0),
            ),
        ]

    def __str__(self) -> str:
        return f"Delivery for {self.order_id}"


class Invoice(models.Model):
    """Coupling/Cohesion: stores computed invoice totals separately from
    order state. It is cohesive on billing math and only couples to Order.
    """
    invoice_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name="invoice")
    total_product_price_excl_vat = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    vat_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_product_price_incl_vat = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    delivery_fee = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_amount_to_pay = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                name="ck_invoices_amounts_non_negative",
                condition=(
                    Q(total_product_price_excl_vat__gte=0)
                    & Q(vat_amount__gte=0)
                    & Q(total_product_price_incl_vat__gte=0)
                    & Q(delivery_fee__gte=0)
                    & Q(total_amount_to_pay__gte=0)
                ),
            ),
            models.CheckConstraint(
                name="ck_invoices_total_product_incl_formula",
                condition=Q(
                    total_product_price_incl_vat=F("total_product_price_excl_vat") + F("vat_amount")
                ),
            ),
            models.CheckConstraint(
                name="ck_invoices_total_amount_formula",
                condition=Q(
                    total_amount_to_pay=F("total_product_price_incl_vat") + F("delivery_fee")
                ),
            ),
        ]

    def __str__(self) -> str:
        return f"Invoice {self.invoice_id}"
