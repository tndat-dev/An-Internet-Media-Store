from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app, render_order


def test_health():
    with TestClient(app) as client:
        response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["service"] == "order-service"


def test_render_order_contract():
    now = datetime.now(timezone.utc)
    value = render_order({"order_id": uuid4(), "order_token": uuid4(), "cancel_token": uuid4(), "status": "PENDING_PAYMENT", "total_amount": Decimal("20"), "items": [{"productId": "p", "productTitle": "Book", "unitPrice": "10", "quantity": 2}], "delivery_info": None, "created_at": now, "updated_at": now})
    assert value["items"][0]["lineAmountExclVat"] == "20"
