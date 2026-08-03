import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("carts", "0001_initial"),
        ("products", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Order",
            fields=[
                ("order_id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("status", models.CharField(choices=[("PENDING_PAYMENT", "Pending payment"), ("PENDING_PROCESSING", "Pending processing"), ("APPROVED", "Approved"), ("REJECTED", "Rejected"), ("CANCELLED", "Cancelled")], default="PENDING_PAYMENT", max_length=24)),
                ("total_amount", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("order_view_token", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("cancel_token", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("processed_by", models.CharField(blank=True, max_length=100)),
                ("processed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("cart", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="orders", to="carts.cart")),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="Invoice",
            fields=[
                ("invoice_id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("total_product_price_excl_vat", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("vat_amount", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("total_product_price_incl_vat", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("delivery_fee", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("total_amount_to_pay", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("order", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="invoice", to="orders.order")),
            ],
        ),
        migrations.CreateModel(
            name="DeliveryInfo",
            fields=[
                ("delivery_info_id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("customer_name", models.CharField(max_length=255)),
                ("phone_number", models.CharField(max_length=30)),
                ("email", models.EmailField(max_length=254)),
                ("delivery_province", models.CharField(max_length=100)),
                ("delivery_address", models.TextField()),
                ("delivery_method", models.CharField(default="STANDARD", max_length=40)),
                ("delivery_instructions", models.TextField(blank=True)),
                ("expected_date", models.DateField(blank=True, null=True)),
                ("shipping_fee", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("order", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="delivery_info", to="orders.order")),
            ],
        ),
        migrations.CreateModel(
            name="OrderItem",
            fields=[
                ("order_item_id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("product_title", models.CharField(max_length=255)),
                ("unit_price", models.DecimalField(decimal_places=2, max_digits=14)),
                ("quantity", models.PositiveIntegerField()),
                ("line_amount_excl_vat", models.DecimalField(decimal_places=2, max_digits=14)),
                ("line_amount_incl_vat", models.DecimalField(decimal_places=2, max_digits=14)),
                ("order", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="items", to="orders.order")),
                ("product", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="order_items", to="products.product")),
            ],
            options={
                "ordering": ["product_title"],
            },
        ),
        migrations.AddConstraint(
            model_name="orderitem",
            constraint=models.UniqueConstraint(fields=("order", "product"), name="uq_order_items_order_product"),
        ),
    ]
