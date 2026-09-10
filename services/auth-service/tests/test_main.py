from fastapi.testclient import TestClient

from app.main import RegisterRequest, admin_base, app, client_id, map_user, token_from_header


def test_health():
    with TestClient(app) as client:
        response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["service"] == "auth-service"


def test_role_mapping_and_legacy_token_header():
    assert token_from_header("Token abc") == "abc"
    user = map_user({"sub": "1", "preferred_username": "dat", "realm_access": {"roles": ["product-manager"]}})
    assert user["roles"] == ["PRODUCT_MANAGER"]


def test_keycloak_contract_defaults():
    assert client_id() == "aims-app"
    assert admin_base().endswith("/auth")
    assert RegisterRequest(username="buyer", email="buyer@example.test", password="secret123").fullName == ""
