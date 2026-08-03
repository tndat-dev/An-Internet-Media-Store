from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.products.models import ProductStatus, ProductType
from apps.products.services import ProductService


def product_payload(**overrides):
    payload = {
        "product_type": ProductType.BOOK,
        "title": "The Clean Coder",
        "category": "Book",
        "general_description": "A practical guide to professional software development.",
        "height": Decimal("20.00"),
        "width": Decimal("14.00"),
        "length": Decimal("3.00"),
        "weight": Decimal("0.80"),
        "barcode": "BOOK-001",
        "image_url": "",
        "original_value": Decimal("100000.00"),
        "current_price": Decimal("120000.00"),
        "stock_quantity": 8,
        "type_details": {
            "authors": "Robert C. Martin",
            "cover_type": "Hardcover",
            "publisher": "Prentice Hall",
            "publication_date": "2011-05-13",
            "language": "English",
            "genre": "Software Engineering",
        },
    }
    payload.update(overrides)
    return payload


@pytest.mark.django_db
def test_customer_product_list_excludes_deleted_products():
    ProductService.create_product(data=product_payload(), manager_id="lam")
    ProductService.create_product(
        data=product_payload(
            title="Deleted Book",
            barcode="BOOK-002",
            stock_quantity=0,
            status=ProductStatus.DELETED,
        ),
        manager_id="lam",
    )

    response = APIClient().get("/api/products/?scope=customer")

    assert response.status_code == 200
    assert [product["title"] for product in response.json()["results"]] == ["The Clean Coder"]


@pytest.mark.django_db
def test_customer_product_list_without_filters_returns_twenty_products():
    for index in range(22):
        ProductService.create_product(
            data=product_payload(
                title=f"Catalog Product {index:02d}",
                barcode=f"BOOK-{index:03d}",
            ),
            manager_id="lam",
        )

    response = APIClient().get("/api/products/?scope=customer")

    assert response.status_code == 200
    assert len(response.json()["results"]) == 20


@pytest.mark.django_db
def test_customer_search_results_are_paginated():
    # 25 matching products -> 20 on page 1, 5 on page 2 (PageNumberPagination).
    for index in range(25):
        ProductService.create_product(
            data=product_payload(
                title=f"Django Guide {index:02d}",
                barcode=f"BOOK-{index:03d}",
            ),
            manager_id="lam",
        )

    page_one = APIClient().get("/api/products/?scope=customer&search=django")
    assert page_one.status_code == 200
    assert page_one.json()["count"] == 25
    assert len(page_one.json()["results"]) == 20
    assert page_one.json()["next"] is not None

    page_two = APIClient().get("/api/products/?scope=customer&search=django&page=2")
    assert page_two.status_code == 200
    assert len(page_two.json()["results"]) == 5
    assert page_two.json()["previous"] is not None


@pytest.mark.django_db
def test_customer_product_list_searches_by_title():
    ProductService.create_product(data=product_payload(title="Clean Architecture"), manager_id="lam")
    ProductService.create_product(
        data=product_payload(title="Domain-Driven Design", barcode="BOOK-002"),
        manager_id="lam",
    )

    response = APIClient().get("/api/products/?scope=customer&search=clean")

    assert response.status_code == 200
    assert [product["title"] for product in response.json()["results"]] == ["Clean Architecture"]


@pytest.mark.django_db
def test_customer_product_list_filters_by_category():
    ProductService.create_product(data=product_payload(), manager_id="lam")
    ProductService.create_product(
        data=product_payload(title="Daily Chronicle", category="Newspaper", barcode="NEWS-001"),
        manager_id="lam",
    )

    response = APIClient().get("/api/products/?scope=customer&category=Newspaper")

    assert response.status_code == 200
    assert [product["category"] for product in response.json()["results"]] == ["Newspaper"]


@pytest.mark.django_db
def test_customer_product_list_filters_by_price_range():
    ProductService.create_product(data=product_payload(current_price=Decimal("120000.00")), manager_id="lam")
    ProductService.create_product(
        data=product_payload(
            title="Premium Book",
            barcode="BOOK-002",
            original_value=Decimal("200000.00"),
            current_price=Decimal("250000.00"),
        ),
        manager_id="lam",
    )

    response = APIClient().get("/api/products/?scope=customer&min_price=100000&max_price=150000")

    assert response.status_code == 200
    assert [product["title"] for product in response.json()["results"]] == ["The Clean Coder"]


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("product_type", "barcode", "type_details", "expected_key"),
    [
        (
            ProductType.BOOK,
            "BOOK-001",
            {"authors": "Robert C. Martin", "cover_type": "Hardcover", "publisher": "Prentice Hall", "publication_date": "2011-05-13"},
            "authors",
        ),
        (
            ProductType.CD,
            "CD-001",
            {"artists": "Yo-Yo Ma", "record_label": "Sony", "tracklist": "Prelude; Allemande", "genre": "Classical"},
            "artists",
        ),
        (
            ProductType.DVD,
            "DVD-001",
            {"director": "David Attenborough", "disc_type": "Blu-ray", "runtime_minutes": 50, "studio": "BBC", "language": "English", "subtitles": "English"},
            "director",
        ),
        (
            ProductType.NEWSPAPER,
            "NEWS-001",
            {"publisher": "Daily Chronicle", "editor_in_chief": "Jane Doe", "publication_date": "2026-01-01"},
            "publisher",
        ),
    ],
)
def test_customer_product_detail_returns_type_specific_fields(
    product_type,
    barcode,
    type_details,
    expected_key,
):
    product = ProductService.create_product(
        data=product_payload(
            product_type=product_type,
            title=f"{product_type} Product",
            category=product_type.title(),
            barcode=barcode,
            type_details=type_details,
        ),
        manager_id="lam",
    )

    response = APIClient().get(f"/api/products/{product.product_id}/?scope=customer")

    assert response.status_code == 200
    assert expected_key in response.json()["type_details"]


@pytest.mark.django_db
def test_customer_product_detail_returns_404_for_deleted_product():
    product = ProductService.create_product(
        data=product_payload(stock_quantity=0, status=ProductStatus.DELETED),
        manager_id="lam",
    )

    response = APIClient().get(f"/api/products/{product.product_id}/?scope=customer")

    assert response.status_code == 404


@pytest.mark.django_db
def test_customer_product_detail_returns_deactivated_product_as_unavailable():
    product = ProductService.create_product(
        data=product_payload(status=ProductStatus.DEACTIVATED),
        manager_id="lam",
    )

    response = APIClient().get(f"/api/products/{product.product_id}/?scope=customer")

    assert response.status_code == 200
    assert response.json()["status"] == ProductStatus.DEACTIVATED
    assert response.json()["is_available"] is False
