from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app, render_cart


def test_health():
    with TestClient(app) as client:
        response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["service"] == "cart-service"


def test_cart_totals():
    result = render_cart({"cart_id": uuid4(), "cart_token": "x", "status": "ACTIVE"}, [{"cart_item_id": uuid4(), "product_id": "p", "product_title": "Book", "product_type": "BOOK", "image_url": "", "unit_price": Decimal("12.50"), "quantity": 2}])
    assert result["subtotalExclVat"] == "25.00"
    assert result["totalItems"] == 2
