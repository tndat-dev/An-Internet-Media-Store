from fastapi.testclient import TestClient
import os
import uuid

from app.main import Detector, TelemetryEvent, app


def test_health():
    with TestClient(app) as client: response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["model"] == "IsolationForest"


def test_detector_warmup_is_not_anomaly():
    detector = Detector()
    assert detector.score(TelemetryEvent(source="t", eventType="exec").features()) == (False, None)


def test_database_history_warms_detector_across_replicas():
    if not os.getenv("DATABASE_URL"):
        return
    event = {
        "source": f"pytest-{uuid.uuid4()}",
        "eventType": "process_exec",
        "severity": 10,
        "syscallRate": 9999,
        "networkRate": 9999,
        "deniedCount": 99,
    }
    with TestClient(app) as client:
        for _ in range(33):
            response = client.post("/api/security/events", json=event)
            assert response.status_code == 202
        assert response.json()["score"] is not None
