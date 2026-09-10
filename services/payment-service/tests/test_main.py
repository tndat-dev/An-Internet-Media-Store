from decimal import Decimal

from fastapi.testclient import TestClient

from app.main import PaymentRequest, app


def test_health():
    with TestClient(app) as client:
        response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["service"] == "payment-service"


def test_payment_contract():
    value = PaymentRequest(orderId="order-1", amount=Decimal("100.00"))
    assert value.provider == "VIETQR"
