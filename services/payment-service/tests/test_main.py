import asyncio
from decimal import Decimal

from fastapi.testclient import TestClient

from uuid import uuid4

from app.main import PaymentRequest, VietQRRequest, app, create_vietqr, runtime, vietqr_response


def test_health():
    with TestClient(app) as client:
        response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["service"] == "payment-service"


def test_payment_contract():
    value = PaymentRequest(orderId="order-1", amount=Decimal("100.00"))
    assert value.provider == "VIETQR"


def test_inventory_event_is_published_as_durable_rabbit_task(monkeypatch):
    published = []

    class Exchange:
        async def publish(self, message, routing_key):
            published.append((message, routing_key))

    monkeypatch.setattr(runtime, "task_exchange", Exchange())
    asyncio.run(runtime.publish_payment_task({
        "eventId": "inventory-event-1",
        "eventType": "InventoryReserved",
        "aggregateId": "order-1",
        "correlationId": "checkout-1",
        "payload": {"totalAmount": "100.00", "currency": "VND"},
    }))
    assert published[0][1] == "payment.execute"
    assert published[0][0].delivery_mode.value == 2


def test_vietqr_contract_exposes_provider_qr_payload():
    row = {"payment_id": uuid4(), "order_id": "order-1", "amount": Decimal("35200"), "currency": "VND", "status": "PENDING", "provider_payload": {"content": "AIMS-ABC", "qrCode": "000201010212", "qrLink": "https://example.test/qr.png"}}
    value = vietqr_response(row)
    assert value["qr_code"] == "000201010212"
    assert value["qr_payload"] == "000201010212"
    assert value["qr_link"] == "https://example.test/qr.png"


def test_payment_config_does_not_expose_secrets(monkeypatch):
    monkeypatch.setenv("PAYPAL_CLIENT_ID", "public-client")
    monkeypatch.setenv("PAYPAL_CLIENT_SECRET", "private-secret")
    with TestClient(app) as client:
        response = client.get("/api/payments/config/")
    assert response.status_code == 200
    assert response.json()["paypalClientId"] == "public-client"
    assert "private-secret" not in response.text


def test_vietqr_uses_server_invoice_amount(monkeypatch):
    captured = {}
    payment_id = uuid4()

    async def fake_invoice(_order_id):
        return {"totalAmountToPay": "35200.00"}

    async def fake_pending(order_id, amount):
        captured["pending_amount"] = amount
        return {"payment_id": payment_id, "order_id": order_id, "amount": amount, "currency": "VND", "status": "PENDING", "provider_payload": {}}

    async def fake_update(_payment_id, provider_payload):
        return {"payment_id": payment_id, "order_id": "order-1", "amount": Decimal("35200"), "currency": "VND", "status": "PENDING", "provider_payload": provider_payload}

    class Response:
        status_code = 200

        def __init__(self, payload):
            self.payload = payload

        def json(self):
            return self.payload

    class Client:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, url, **kwargs):
            if url.endswith("token_generate"):
                return Response({"access_token": "token"})
            captured["provider_amount"] = kwargs["json"]["amount"]
            return Response({"status": "SUCCESS", "qrCode": "000201", "qrLink": "https://example.test/qr.png"})

    monkeypatch.setattr("app.main.order_invoice", fake_invoice)
    monkeypatch.setattr(runtime, "create_pending", fake_pending)
    monkeypatch.setattr(runtime, "update_provider_payload", fake_update)
    monkeypatch.setattr("app.main.httpx.AsyncClient", Client)
    monkeypatch.setenv("VIETQR_USERNAME", "user")
    monkeypatch.setenv("VIETQR_PASSWORD", "password")
    result = asyncio.run(create_vietqr(VietQRRequest(order_id="order-1", amount=Decimal("1"))))
    assert captured == {"pending_amount": Decimal("35200.00"), "provider_amount": 35200}
    assert result["amount"] == "35200"
