import asyncio

from fastapi.testclient import TestClient

from app.main import EventEnvelope, NotificationRuntime, app, runtime


def test_health_is_independent_from_monolith():
    with TestClient(app) as client:
        response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["service"] == "notification-service"


def test_accepts_versioned_payment_event(monkeypatch):
    event = {
        "eventId": "event-1",
        "eventType": "PaymentCompleted",
        "eventVersion": 1,
        "occurredAt": "2026-09-09T00:00:00Z",
        "aggregateId": "payment-1",
        "correlationId": "order-1",
        "payload": {"amount": "120000.00", "currency": "VND"},
    }
    async def record_task(value):
        runtime.processed += 1

    monkeypatch.setattr(runtime, "rabbit_ready", True)
    monkeypatch.setattr(runtime, "publish_task", record_task)
    with TestClient(app) as client:
        runtime.rabbit_ready = True
        response = client.post("/api/notifications/events", json=event)
    assert response.status_code == 202
    assert response.json()["accepted"] is True
    assert runtime.processed >= 1


def test_payment_event_is_published_as_durable_rabbit_task(monkeypatch):
    published = []

    class Exchange:
        async def publish(self, message, routing_key):
            published.append((message, routing_key))

    event = EventEnvelope.model_validate({
        "eventId": "payment-event-1",
        "eventType": "PaymentCompleted",
        "eventVersion": 1,
        "occurredAt": "2026-09-13T00:00:00Z",
        "aggregateId": "order-1",
        "correlationId": "checkout-1",
        "payload": {},
    })
    monkeypatch.setattr(runtime, "task_exchange", Exchange())
    asyncio.run(runtime.publish_task(event))
    assert published[0][1] == "notification.deliver"
    assert published[0][0].delivery_mode.value == 2


def test_order_lifecycle_event_is_supported(monkeypatch):
    published = []

    class Exchange:
        async def publish(self, message, routing_key):
            published.append((message, routing_key))

    event = EventEnvelope.model_validate({
        "eventId": "order-approved-event-1",
        "eventType": "OrderApproved",
        "eventVersion": 1,
        "occurredAt": "2026-09-15T00:00:00Z",
        "aggregateId": "order-1",
        "correlationId": "order-1",
        "payload": {"email": "buyer@example.test"},
    })
    monkeypatch.setattr(runtime, "task_exchange", Exchange())
    asyncio.run(runtime.publish_task(event))
    assert published[0][1] == "notification.deliver"


def test_delivery_channel_is_injected_without_changing_kafka_runtime():
    sent = []

    class FakeChannel:
        async def send(self, event):
            sent.append(event.eventId)

    service = NotificationRuntime(channel=FakeChannel())
    event = EventEnvelope.model_validate({
        "eventId": "event-1", "eventType": "OrderApproved", "eventVersion": 1,
        "occurredAt": "2026-09-15T00:00:00Z", "aggregateId": "order-1",
        "correlationId": "order-1", "payload": {},
    })
    asyncio.run(service.deliver(event))
    assert sent == ["event-1"]
    assert service.processed == 1
