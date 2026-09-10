from fastapi.testclient import TestClient

from app.main import ACTION_WEIGHT, Interaction, app


def test_health():
    with TestClient(app) as client:
        response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["service"] == "search-recommendation-service"


def test_interaction_weights():
    assert Interaction(subjectId="u", productId="p", action="PURCHASE").action == "PURCHASE"
    assert ACTION_WEIGHT["PURCHASE"] > ACTION_WEIGHT["VIEW"]
