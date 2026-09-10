from fastapi.testclient import TestClient

from app.main import Detector, TelemetryEvent, app


def test_health():
    with TestClient(app) as client: response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["model"] == "IsolationForest"


def test_detector_warmup_is_not_anomaly():
    detector = Detector()
    assert detector.score(TelemetryEvent(source="t", eventType="exec").features()) == (False, None)
