from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient

import pytest
from fastapi import HTTPException

from app.main import ProductInput, app, encode_product, validate_product


def test_health():
    with TestClient(app) as client:
        response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["service"] == "catalog-service"


def test_product_encoding_is_frontend_compatible():
    product = encode_product({"product_id": uuid4(), "price": Decimal("10.00"), "original_value": Decimal("12"), "height": Decimal("1"), "width": Decimal("1"), "length": Decimal("1"), "weight": Decimal("1.2"), "status": "ACTIVE", "stock_quantity": 2})
    assert isinstance(product["product_id"], str)
    assert product["price"] == "10.00"


def test_problem_statement_price_boundary_and_type_fields():
    valid = ProductInput(title="Book", product_type="BOOK", current_price=Decimal("30"), original_value=Decimal("100"), type_details={"authors": "A", "cover_type": "PAPERBACK", "publisher": "P", "publication_date": "2026-01-01"})
    validate_product(valid)
    invalid = valid.model_copy(update={"current_price": Decimal("151")})
    with pytest.raises(HTTPException):
        validate_product(invalid)
