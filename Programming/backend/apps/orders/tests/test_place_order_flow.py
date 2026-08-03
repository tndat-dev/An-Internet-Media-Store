from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.carts.services import CartService
from apps.orders.models import Order
from apps.products.models import Product, ProductType


pytestmark = pytest.mark.django_db


def create_product(**overrides):
    data = {
        "product_type": ProductType.BOOK,
        "title": "Domain-Driven Design",
        "category": "Book",
        "height": Decimal("1.00"),
        "width": Decimal("10.00"),
        "length": Decimal("15.00"),
        "weight": Decimal("0.50"),
        "barcode": "ORDER-001",
        "original_value": Decimal("100000.00"),
        "current_price": Decimal("90000.00"),
        "stock_quantity": 5,
    }
    data.update(overrides)
    return Product.objects.create(**data)


def delivery_payload(**overrides):
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


def test_create_draft_order_rejects_empty_cart():
    client = APIClient()

    response = client.post("/api/orders/draft/", {}, format="json", HTTP_X_CART_TOKEN="empty-token")

    assert response.status_code == 400
    assert "EMPTY_CART" in str(response.data)


def test_create_draft_order_rejects_cart_with_insufficient_stock():
    product = create_product(stock_quantity=1, barcode="ORDER-STOCK-001")
    cart_token = "draft-stock-token"
    CartService.add_item(cart_token, str(product.product_id), 2)
    client = APIClient()

    response = client.post("/api/orders/draft/", {}, format="json", HTTP_X_CART_TOKEN=cart_token)

    assert response.status_code == 400
    assert response.data["cart"][0]["reason"] == "INSUFFICIENT_STOCK"
    assert response.data["cart"][0]["availableQuantity"] == 1
    assert response.data["cart"][0]["missingQuantity"] == 1


def test_place_order_flow_creates_invoice_and_public_lookup():
    product = create_product()
    cart_token = "place-order-token"
    CartService.add_item(cart_token, str(product.product_id), 2)
    client = APIClient()

    draft_response = client.post("/api/orders/draft/", {}, format="json", HTTP_X_CART_TOKEN=cart_token)

    assert draft_response.status_code == 201
    order_id = draft_response.data["orderId"]
    assert draft_response.data["status"] == "PENDING_PAYMENT"
    assert draft_response.data["items"][0]["productTitle"] == "Domain-Driven Design"
    assert draft_response.data["items"][0]["unitPrice"] == "90000.00"

    delivery_response = client.post(
        f"/api/orders/{order_id}/delivery/",
        delivery_payload(),
        format="json",
        HTTP_X_CART_TOKEN=cart_token,
    )

    assert delivery_response.status_code == 200
    assert delivery_response.data["invoice"]["subtotalExclVat"] == "180000.00"
    assert delivery_response.data["invoice"]["vatAmount"] == "18000.00"
    assert delivery_response.data["invoice"]["deliveryFee"] == "0.00"
    assert delivery_response.data["invoice"]["totalAmountToPay"] == "198000.00"

    invoice_response = client.get(f"/api/orders/{order_id}/invoice/")

    assert invoice_response.status_code == 200
    assert invoice_response.data["totalAmountToPay"] == "198000.00"

    confirm_response = client.post("/api/orders/", {"orderId": order_id}, format="json")

    assert confirm_response.status_code == 200
    assert confirm_response.data["status"] == "PENDING_PAYMENT"
    order_token = confirm_response.data["orderToken"]

    lookup_response = client.get(f"/api/orders/{order_token}/")

    assert lookup_response.status_code == 200
    assert lookup_response.data["orderId"] == order_id
    assert Order.objects.get(order_id=order_id).status == "PENDING_PAYMENT"


def test_delivery_validation_returns_field_errors():
    product = create_product(barcode="ORDER-002")
    cart_token = "invalid-delivery-token"
    CartService.add_item(cart_token, str(product.product_id), 1)
    client = APIClient()
    draft_response = client.post("/api/orders/draft/", {}, format="json", HTTP_X_CART_TOKEN=cart_token)
    order_id = draft_response.data["orderId"]

    response = client.post(
        f"/api/orders/{order_id}/delivery/",
        delivery_payload(customerName="Nguyen123", email="not-email", deliveryProvince=""),
        format="json",
        HTTP_X_CART_TOKEN=cart_token,
    )

    assert response.status_code == 400
    assert response.data["name"] == "INVALID_CUSTOMER_NAME"
    assert response.data["email"] == "INVALID_EMAIL"
    assert response.data["province"] == "INVALID_PROVINCE"


def test_delivery_rechecks_stock_before_persisting():
    product = create_product(stock_quantity=3, barcode="ORDER-DELIVERY-STOCK-001")
    cart_token = "delivery-stock-token"
    CartService.add_item(cart_token, str(product.product_id), 2)
    client = APIClient()
    draft_response = client.post("/api/orders/draft/", {}, format="json", HTTP_X_CART_TOKEN=cart_token)
    order_id = draft_response.data["orderId"]

    Product.objects.filter(product_id=product.product_id).update(stock_quantity=1)

    response = client.post(
        f"/api/orders/{order_id}/delivery/",
        delivery_payload(),
        format="json",
        HTTP_X_CART_TOKEN=cart_token,
    )

    assert response.status_code == 400
    assert response.data["cart"][0]["reason"] == "INSUFFICIENT_STOCK"
    assert response.data["cart"][0]["availableQuantity"] == 1


def test_mark_paid_transitions_order_to_pending_processing():
    product = create_product(barcode="ORDER-004")
    cart_token = "mark-paid-token"
    CartService.add_item(cart_token, str(product.product_id), 1)
    client = APIClient()

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

    response = client.post(f"/api/orders/{order_id}/mark-paid/", {}, format="json")

    assert response.status_code == 200
    assert response.data["status"] == "PENDING_PROCESSING"
    assert Order.objects.get(order_id=order_id).status == "PENDING_PROCESSING"

    # Idempotent: a retried payment callback must not error.
    retry = client.post(f"/api/orders/{order_id}/mark-paid/", {}, format="json")
    assert retry.status_code == 200
    assert retry.data["status"] == "PENDING_PROCESSING"


def test_confirm_order_requires_invoice():
    product = create_product(barcode="ORDER-003")
    cart_token = "confirm-missing-invoice-token"
    CartService.add_item(cart_token, str(product.product_id), 1)
    client = APIClient()
    draft_response = client.post("/api/orders/draft/", {}, format="json", HTTP_X_CART_TOKEN=cart_token)

    response = client.post("/api/orders/", {"orderId": draft_response.data["orderId"]}, format="json")

    assert response.status_code == 400
    assert "Delivery information is required" in str(response.data)
