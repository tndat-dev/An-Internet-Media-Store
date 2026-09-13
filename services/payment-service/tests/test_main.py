import asyncio
from decimal import Decimal

from fastapi.testclient import TestClient

from app.main import PaymentRequest, app, runtime


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
