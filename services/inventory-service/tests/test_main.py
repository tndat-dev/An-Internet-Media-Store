import os

import pytest
from fastapi.testclient import TestClient

from app.main import EventEnvelope, app


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
