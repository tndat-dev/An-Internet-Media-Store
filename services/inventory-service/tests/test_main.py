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


def test_adjust_returns_service_unavailable_without_database():
    with TestClient(app) as client:
        response = client.post("/api/inventory/product-1/adjust", json={"delta": 5})
    assert response.status_code == 503
