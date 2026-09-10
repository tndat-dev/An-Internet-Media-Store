from fastapi.testclient import TestClient

from app.main import app, upstream_for


def test_health():
    with TestClient(app) as client:
        response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["service"] == "api-gateway"


def test_domain_routing_is_explicit():
    assert upstream_for("/api/products/").startswith("http://catalog-service")
    assert upstream_for("/api/search/").startswith("http://search-recommendation-service")
    assert upstream_for("/api/unknown/") is None
