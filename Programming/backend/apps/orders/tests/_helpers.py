"""Shared helpers for order lifecycle tests (not collected: no test_ prefix)."""

from decimal import Decimal

from rest_framework.test import APIClient

from apps.carts.services import CartService
from apps.products.models import Product, ProductType
from apps.users.models import AuthToken, Role, User, UserRole


def make_user_token(username: str = "mgr", role_name: str | None = "PRODUCT_MANAGER") -> tuple[User, str]:
    """Create an internal user (optionally with a role) and return (user, token_key)."""
    user = User.objects.create(username=username, email=f"{username}@aims.local")
    if role_name:
        role, _ = Role.objects.get_or_create(role_name=role_name)
        UserRole.objects.create(user=user, role=role)
    token = AuthToken.create_for(user)
    return user, token.key


def create_product(**overrides) -> Product:
    data = {
        "product_type": ProductType.BOOK,
        "title": "Domain-Driven Design",
        "category": "Book",
        "height": Decimal("1.00"),
        "width": Decimal("10.00"),
        "length": Decimal("15.00"),
        "weight": Decimal("0.50"),
        "barcode": "FULFILL-001",
        "original_value": Decimal("100000.00"),
        "current_price": Decimal("90000.00"),
        "stock_quantity": 5,
    }
    data.update(overrides)
    return Product.objects.create(**data)


def delivery_payload(**overrides) -> dict:
    data = {
        "customerName": "Nguyen Van A",
        "phoneNumber": "0123456789",
        "email": "a@example.com",
        "deliveryProvince": "Ha Noi",
        "deliveryAddress": "12/5 ABC Street",
        "deliveryMethod": "STANDARD",
        "deliveryInstructions": "Call before delivery",
    }
    data.update(overrides)
    return data


def place_confirmed_order(product: Product, quantity: int, cart_token: str) -> str:
    """Drive draft -> delivery -> confirm and return the order id (PENDING_PAYMENT)."""
    client = APIClient()
    CartService.add_item(cart_token, str(product.product_id), quantity)
    order_id = client.post(
        "/api/orders/draft/", {}, format="json", HTTP_X_CART_TOKEN=cart_token
    ).data["orderId"]
    client.post(
        f"/api/orders/{order_id}/delivery/",
        delivery_payload(),
        format="json",
        HTTP_X_CART_TOKEN=cart_token,
    )
    client.post("/api/orders/", {"orderId": order_id}, format="json")
    return order_id
