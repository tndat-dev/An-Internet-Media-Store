import os
import asyncio
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import EventEnvelope, app, runtime


def test_health_is_independent_from_monolith():
    with TestClient(app) as client:
        response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["service"] == "inventory-service"


def test_order_event_validates_items():
    event = EventEnvelope.model_validate(
        {
            "eventId": "event-1",
            "eventType": "OrderCreated",
            "eventVersion": 1,
            "occurredAt": "2026-09-09T00:00:00Z",
            "aggregateId": "order-1",
            "correlationId": "checkout-1",
            "payload": {"items": [{"productId": "product-1", "quantity": 2}]},
        }
    )
    assert event.order_items()[0].quantity == 2


def test_adjust_uses_ci_postgres_when_configured(monkeypatch):
    if not os.getenv("DATABASE_URL"):
        pytest.skip("DATABASE_URL is not configured")
    async def allow_test_manager(_authorization):
        return None
    monkeypatch.setattr("app.main.require_product_manager", allow_test_manager)
    with TestClient(app) as client:
        response = client.post("/api/inventory/product-1/adjust", json={"delta": 5, "reason": "CI stock receipt"}, headers={"Authorization": "Bearer test"})
    assert response.status_code == 200
    assert response.json()["available"] >= 5


def test_reservation_is_released_or_committed_from_order_lifecycle():
    if not os.getenv("DATABASE_URL"):
        pytest.skip("DATABASE_URL is not configured")
    product_id = f"product-{uuid.uuid4()}"

    def event(order_id, event_id, event_type):
        return EventEnvelope.model_validate({
            "eventId": event_id,
            "eventType": event_type,
            "eventVersion": 1,
            "occurredAt": "2026-09-15T00:00:00Z",
            "aggregateId": order_id,
            "correlationId": order_id,
            "payload": {"items": [{"productId": product_id, "quantity": 2}]},
        })

    async def scenario():
        await runtime.adjust(product_id, 5)
        cancelled_order = f"order-{uuid.uuid4()}"
        await runtime.reserve_for_order(event(cancelled_order, f"event-{uuid.uuid4()}", "OrderCreated"))
        reserved = await runtime.stock(product_id)
        assert reserved["available"] == 3 and reserved["reserved"] == 2
        cancel_event = event(cancelled_order, f"event-{uuid.uuid4()}", "OrderCancelled")
        await runtime.finalize_reservation(cancel_event)
        await runtime.finalize_reservation(cancel_event)
        released = await runtime.stock(product_id)
        assert released["available"] == 5 and released["reserved"] == 0

        approved_order = f"order-{uuid.uuid4()}"
        await runtime.reserve_for_order(event(approved_order, f"event-{uuid.uuid4()}", "OrderCreated"))
        await runtime.finalize_reservation(event(approved_order, f"event-{uuid.uuid4()}", "OrderApproved"))
        committed = await runtime.stock(product_id)
        assert committed["available"] == 3 and committed["reserved"] == 0
        batch = await runtime.stocks([product_id, "missing-product"])
        assert len(batch) == 1 and batch[0]["product_id"] == product_id

    with TestClient(app):
        asyncio.run(scenario())
