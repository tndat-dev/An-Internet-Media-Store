"""Seed demo users and a realistic 60-item product catalog.

Idempotent: products are matched by barcode, so re-running will not create
duplicates. Safe to run against a fresh Supabase/Postgres database.

Usage:
    python manage.py seed_demo
"""

from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand

from apps.products.demo_catalog import DEMO_PRODUCTS
from apps.products.models import Product, ProductType
from apps.products.services import ProductService
from apps.users.models import Role, User, UserRole


DEMO_ROLES = [
    ("ADMIN", "Administrator - manages internal user accounts and roles."),
    ("PRODUCT_MANAGER", "Product Manager - manages products and stock."),
    ("CUSTOMER", "Customer - self-registered shopper account."),
]

# (username, email, password, role_name)
DEMO_USERS = [
    ("admin", "admin@aims.local", "admin12345", "ADMIN"),
    ("linh", "linh@aims.local", "linh12345", "PRODUCT_MANAGER"),
    ("lam", "lam@aims.local", "lam12345", "PRODUCT_MANAGER"),
]


# Dimensions are shared by demo rows; individual media-specific data lives in demo_catalog.py.
COMMON_DIMENSIONS = {"height": "1.00", "width": "10.00", "length": "15.00"}


class Command(BaseCommand):
    help = "Seed demo users and products for the AIMS customer/manager flows (idempotent)."

    def handle(self, *args, **options):
        self._seed_users()

        created, skipped, image_backfilled, category_backfilled = 0, 0, 0, 0
        for item in DEMO_PRODUCTS:
            existing_product = Product.objects.filter(barcode=item["barcode"]).first()
            if existing_product:
                changed = False
                if self._backfill_image(existing_product, item):
                    image_backfilled += 1
                    changed = True
                    self.stdout.write(f"  image    {item['barcode']} - {item['title']}")
                if self._backfill_category(existing_product, item):
                    category_backfilled += 1
                    changed = True
                    self.stdout.write(f"  category {item['barcode']} - {item['title']}")
                if not changed:
                    skipped += 1
                    self.stdout.write(f"  skip     {item['barcode']} (already exists)")
                continue

            try:
                ProductService.create_product(data={**item, **COMMON_DIMENSIONS}, manager_id="linh")
            except Exception as error:
                self.stderr.write(self.style.ERROR(f"  fail  {item['barcode']} - {item['title']}: {error}"))
                raise

            created += 1
            self.stdout.write(f"  add   {item['barcode']} - {item['title']}")

        total = Product.objects.count()
        self.stdout.write(
            self.style.SUCCESS(
                "Seed complete: "
                f"{created} created, {skipped} skipped, "
                f"{image_backfilled} images backfilled, {category_backfilled} categories backfilled. "
                f"Total products: {total}."
            )
        )

    def _backfill_image(self, product: Product, item: dict) -> bool:
        image_url = item.get("image_url", "")
        if product.image_url or not image_url:
            return False

        product.image_url = image_url
        product.full_clean()
        product.save(update_fields=["image_url", "updated_at"])
        return True

    # Legacy seed rows stored the medium label ("Book"/"CD"/"DVD"/"Newspaper") in category.
    # Only those rows are rewritten to the real subject; edited categories are never clobbered.
    _LEGACY_CATEGORIES = {label for _, label in ProductType.choices}

    def _backfill_category(self, product: Product, item: dict) -> bool:
        new_category = item.get("category", "")
        if (
            not new_category
            or product.category == new_category
            or product.category not in self._LEGACY_CATEGORIES
        ):
            return False

        product.category = new_category
        product.full_clean()
        product.save(update_fields=["category", "updated_at"])
        return True

    def _seed_users(self):
        roles = {}
        for role_name, description in DEMO_ROLES:
            role, _ = Role.objects.get_or_create(role_name=role_name, defaults={"description": description})
            roles[role_name] = role

        for username, email, password, role_name in DEMO_USERS:
            user, _ = User.objects.get_or_create(
                username=username,
                defaults={"email": email, "password_hash": make_password(password)},
            )
            UserRole.objects.get_or_create(user=user, role=roles[role_name])

        self.stdout.write(f"  users: {User.objects.count()} total, roles: {Role.objects.count()} total")
