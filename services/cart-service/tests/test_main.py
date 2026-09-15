from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app, empty_cart, render_cart


def test_health():
    with TestClient(app) as client:
        response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["service"] == "cart-service"


def test_cart_totals():
    result = render_cart({"cart_id": uuid4(), "cart_token": "x", "status": "ACTIVE"}, [{"cart_item_id": uuid4(), "product_id": "p", "product_title": "Book", "product_type": "BOOK", "image_url": "", "unit_price": Decimal("12.50"), "quantity": 2}])
    assert result["subtotalExclVat"] == "25.00"
    assert result["items"][0]["unitWeight"] == "0.5"
    assert result["totalItems"] == 2


def test_unknown_cart_is_rendered_without_persisting():
    result = empty_cart("new-token")
    assert result["cartId"] is None
    assert result["cartToken"] == "new-token"
    assert result["items"] == []
    assert result["canPlaceOrder"] is False


def test_cart_reports_exact_stock_shortage():
    result = render_cart({"cart_id": uuid4(), "cart_token": "x", "status": "ACTIVE"}, [{"cart_item_id": uuid4(), "product_id": "p", "product_title": "Book", "product_type": "BOOK", "image_url": "", "unit_price": Decimal("12.50"), "unit_weight": Decimal("0.5"), "quantity": 3, "available": 1}])
    assert result["canPlaceOrder"] is False
    assert result["stockErrors"][0]["shortageQuantity"] == 2
