from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.products.models import Product, ProductStatus, ProductType


pytestmark = pytest.mark.django_db


def create_product(**overrides):
    data = {
        "product_type": ProductType.BOOK,
        "title": "Clean Architecture",
        "category": "Book",
        "height": Decimal("1.00"),
        "width": Decimal("10.00"),
        "length": Decimal("15.00"),
        "weight": Decimal("0.50"),
        "barcode": "CART-001",
        "original_value": Decimal("100000.00"),
        "current_price": Decimal("90000.00"),
        "stock_quantity": 5,
        "status": ProductStatus.ACTIVE,
    }
    data.update(overrides)
    return Product.objects.create(**data)


def test_cart_api_add_update_remove_item():
    product = create_product()
    client = APIClient()
    headers = {"HTTP_X_CART_TOKEN": "cart-api-token"}

    add_response = client.post(
        "/api/cart/items/",
        {"productId": str(product.product_id), "quantity": 2},
        format="json",
        **headers,
    )

    assert add_response.status_code == 201
    assert add_response.data["totalItems"] == 2
    item_id = add_response.data["items"][0]["cartItemId"]

    update_response = client.patch(
        f"/api/cart/items/{item_id}/",
        {"quantity": 3},
        format="json",
        **headers,
    )

    assert update_response.status_code == 200
    assert update_response.data["items"][0]["quantity"] == 3

    delete_response = client.delete(f"/api/cart/items/{item_id}/", **headers)

    assert delete_response.status_code == 200
    assert delete_response.data["items"] == []


def test_cart_api_update_allows_insufficient_stock_but_returns_warning():
    product = create_product(stock_quantity=1, barcode="CART-UPDATE-STOCK-001")
    client = APIClient()
    headers = {"HTTP_X_CART_TOKEN": "cart-update-stock-token"}
    add_response = client.post(
        "/api/cart/items/",
        {"productId": str(product.product_id), "quantity": 1},
        format="json",
        **headers,
    )

    response = client.patch(
        f"/api/cart/items/{add_response.data['items'][0]['cartItemId']}/",
        {"quantity": 3},
        format="json",
        **headers,
    )

    assert response.status_code == 200
    assert response.data["items"][0]["quantity"] == 3
    assert response.data["items"][0]["stockWarning"]["missingQuantity"] == 2
    assert response.data["stockErrors"][0]["availableQuantity"] == 1


def test_cart_api_allows_insufficient_stock_but_returns_warning():
    product = create_product(stock_quantity=1)
    client = APIClient()

    response = client.post(
        "/api/cart/items/",
        {"productId": str(product.product_id), "quantity": 2},
        format="json",
        HTTP_X_CART_TOKEN="stock-token",
    )

    assert response.status_code == 201
    assert response.data["items"][0]["quantity"] == 2
    assert response.data["items"][0]["stockWarning"]["reason"] == "INSUFFICIENT_STOCK"
    assert response.data["items"][0]["stockWarning"]["availableQuantity"] == 1
    assert response.data["items"][0]["stockWarning"]["missingQuantity"] == 1
    assert response.data["stockErrors"][0]["reason"] == "INSUFFICIENT_STOCK"


def test_cart_api_rejects_inactive_product():
    product = create_product(status=ProductStatus.DEACTIVATED, barcode="CART-002")
    client = APIClient()

    response = client.post(
        "/api/cart/items/",
        {"productId": str(product.product_id), "quantity": 1},
        format="json",
        HTTP_X_CART_TOKEN="inactive-token",
    )

    assert response.status_code == 400
    assert "PRODUCT_UNAVAILABLE" in str(response.data)
