from decimal import Decimal

import pytest
from django.contrib.auth.hashers import make_password
from django.core.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.products.models import Product, ProductHistoryActionType, ProductStatus, ProductType
from apps.products.services import ProductService
from apps.users.models import AuthToken, Role, User, UserRole


def _token_for(username: str, role_name: str) -> str:
    user = User.objects.create(
        username=username, email=f"{username}@aims.local", password_hash=make_password("pass12345")
    )
    role, _ = Role.objects.get_or_create(role_name=role_name)
    UserRole.objects.create(user=user, role=role)
    return AuthToken.create_for(user).key


def _api_create_payload(**overrides) -> dict:
    data = {
        "product_type": "BOOK",
        "title": "Perm Book",
        "category": "Book",
        "general_description": "x",
        "height": "20.00",
        "width": "14.00",
        "length": "3.00",
        "weight": "0.80",
        "barcode": "PERM-001",
        "original_value": "100000.00",
        "current_price": "120000.00",
        "stock_quantity": 8,
        "type_details": {
            "authors": "Robert C. Martin",
            "cover_type": "Paperback",
            "publisher": "Pearson",
            "publication_date": "2017-09-20",
        },
    }
    data.update(overrides)
    return data


def product_payload(**overrides):
    payload = {
        "product_type": ProductType.BOOK,
        "title": "Clean Architecture",
        "category": "Book",
        "general_description": "Architecture reference for maintainable systems.",
        "height": Decimal("20.00"),
        "width": Decimal("14.00"),
        "length": Decimal("3.00"),
        "weight": Decimal("0.80"),
        "barcode": "9780134494166",
        "image_url": "",
        "original_value": Decimal("100000.00"),
        "current_price": Decimal("120000.00"),
        "stock_quantity": 8,
        "type_details": {
            "authors": "Robert C. Martin",
            "cover_type": "Paperback",
            "publisher": "Pearson",
            "publication_date": "2017-09-20",
        },
    }
    payload.update(overrides)
    return payload


@pytest.mark.django_db
def test_create_product_logs_history_and_type_details():
    product = ProductService.create_product(data=product_payload(), manager_id="linh")

    assert product.product_id is not None
    assert product.book_details.authors == "Robert C. Martin"
    assert product.histories.filter(action_type=ProductHistoryActionType.CREATE, performed_by__username="linh").exists()


@pytest.mark.django_db
def test_create_product_requires_type_specific_fields():
    # Book requires authors + cover_type + publisher + publication_date (PS).
    payload = product_payload(barcode="REQ-001", type_details={"authors": "Only Author"})
    with pytest.raises(ValidationError):
        ProductService.create_product(data=payload, manager_id="linh")


@pytest.mark.django_db
def test_update_product_requires_stock_adjustment_reason():
    product = ProductService.create_product(data=product_payload(), manager_id="linh")

    with pytest.raises(ValidationError):
        ProductService.update_product(product=product, data={"stock_quantity": 10}, manager_id="linh")


@pytest.mark.django_db
def test_delete_product_with_stock_deactivates_instead_of_deleting():
    product = ProductService.create_product(data=product_payload(), manager_id="linh")

    [changed_product] = ProductService.delete_products(product_ids=[str(product.product_id)], manager_id="linh")

    assert changed_product.status == ProductStatus.DEACTIVATED
    assert changed_product.histories.filter(action_type=ProductHistoryActionType.DEACTIVATE).exists()


@pytest.mark.django_db
def test_delete_product_without_stock_marks_deleted():
    product = ProductService.create_product(
        data=product_payload(barcode="9780132350884", stock_quantity=0),
        manager_id="linh",
    )

    [changed_product] = ProductService.delete_products(product_ids=[str(product.product_id)], manager_id="linh")

    assert changed_product.status == ProductStatus.DELETED
    assert changed_product.histories.filter(action_type=ProductHistoryActionType.DELETE).exists()


@pytest.mark.django_db
def test_delete_request_cannot_include_more_than_ten_products():
    products = [
        ProductService.create_product(
            data=product_payload(barcode=f"BARCODE-{index}", title=f"Product {index}", stock_quantity=0),
            manager_id="linh",
        )
        for index in range(11)
    ]

    with pytest.raises(ValidationError):
        ProductService.delete_products(
            product_ids=[str(product.product_id) for product in products],
            manager_id="linh",
        )


@pytest.mark.django_db
def test_product_create_endpoint_requires_product_manager():
    client = APIClient()
    # No token -> 401 (auth required).
    assert client.post("/api/products/", {}, format="json").status_code == 401
    # Customer token -> 403 (authenticated but lacks PRODUCT_MANAGER role).
    client.credentials(HTTP_AUTHORIZATION=f"Token {_token_for('cust', 'CUSTOMER')}")
    assert client.post("/api/products/", {}, format="json").status_code == 403
    # Product manager token -> 201.
    client.credentials(HTTP_AUTHORIZATION=f"Token {_token_for('mgr', 'PRODUCT_MANAGER')}")
    response = client.post("/api/products/", _api_create_payload(), format="json")
    assert response.status_code == 201
    assert response.data["title"] == "Perm Book"


@pytest.mark.django_db
def test_product_delete_endpoint_requires_product_manager():
    assert APIClient().post("/api/products/delete/", {"product_ids": []}, format="json").status_code == 401

