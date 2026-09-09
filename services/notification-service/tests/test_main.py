from fastapi.testclient import TestClient

from app.main import app, runtime


def test_health_is_independent_from_monolith():
    with TestClient(app) as client:
        response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["service"] == "notification-service"


def test_accepts_versioned_payment_event():
    event = {
        "eventId": "event-1",
        "eventType": "PaymentCompleted",
        "eventVersion": 1,
        "occurredAt": "2026-09-09T00:00:00Z",
        "aggregateId": "payment-1",
        "correlationId": "order-1",
        "payload": {"amount": "120000.00", "currency": "VND"},
    }
    with TestClient(app) as client:
        response = client.post("/api/notifications/events", json=event)
    assert response.status_code == 202
    assert response.json()["accepted"] is True
    assert runtime.processed >= 1
